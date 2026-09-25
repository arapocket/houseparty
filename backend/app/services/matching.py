"""Discover and matching.

Rules baked in here:
  * you only see people who share at least one interest with you
  * ranked by how many interests you share, closest first on a tie
  * inside your own radius, and never widened automatically
  * 21+ everywhere, and no age filtering beyond that
  * people you have already decided on, or blocked either way, are gone
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime

from sqlalchemy import and_, func, or_, select, union_all
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.errors import RuleError
from app.models import (
    DECISION_LIKE,
    PARTY_ACTIVE,
    SUGGESTION_MATCHED,
    SUGGESTION_PENDING,
    Block,
    Decision,
    Interest,
    Match,
    Party,
    Suggestion,
    User,
    UserInterest,
)
from app.services.geo import display_distance_km, distance_expression


def ordered_pair(a: uuid.UUID, b: uuid.UUID) -> tuple[uuid.UUID, uuid.UUID]:
    """Fixed ordering so a pair is stored the same way regardless of who acted."""
    return (a, b) if str(a) < str(b) else (b, a)


def age_on(birthdate: date, today: date | None = None) -> int:
    today = today or date.today()
    had_birthday = (today.month, today.day) >= (birthdate.month, birthdate.day)
    return today.year - birthdate.year - (0 if had_birthday else 1)


def meets_minimum_age(birthdate: date, today: date | None = None) -> bool:
    return age_on(birthdate, today) >= settings.min_age


@dataclass
class DiscoverCandidate:
    user: User
    shared_interests: list[Interest]
    distance_km: int
    suggested_for_party_id: uuid.UUID | None


async def blocked_user_ids(session: AsyncSession, user_id: uuid.UUID) -> set[uuid.UUID]:
    """Blocks cut both ways: neither side sees the other again."""
    rows = await session.execute(
        select(Block.blocker_id, Block.blocked_id).where(
            or_(Block.blocker_id == user_id, Block.blocked_id == user_id)
        )
    )
    out: set[uuid.UUID] = set()
    for blocker, blocked in rows:
        out.add(blocked if blocker == user_id else blocker)
    return out


async def discover(
    session: AsyncSession, me: User, limit: int = 20, offset: int = 0
) -> list[DiscoverCandidate]:
    my_interest_ids = [ui.interest_id for ui in me.interests]
    if not my_interest_ids or me.latitude is None or me.longitude is None:
        return []

    shared = (
        select(
            UserInterest.user_id.label("user_id"),
            func.count().label("shared_count"),
        )
        .where(UserInterest.interest_id.in_(my_interest_ids))
        .group_by(UserInterest.user_id)
        .subquery()
    )

    decided = select(Decision.target_id).where(Decision.actor_id == me.id)
    excluded = await blocked_user_ids(session, me.id)
    excluded.add(me.id)

    distance = distance_expression(User.latitude, User.longitude, me.latitude, me.longitude)

    # Introductions: when a guest suggests someone for a party, the host and
    # the suggested person float to the top of each other's Discover, even if
    # they share no interests. Each row is (the other person, the party).
    host_sees = (
        select(Suggestion.suggested_user_id.label("user_id"), Suggestion.party_id)
        .join(Party, Party.id == Suggestion.party_id)
        .where(
            Suggestion.status == SUGGESTION_PENDING,
            Party.status == PARTY_ACTIVE,
            Party.host_id == me.id,
        )
    )
    suggested_sees = (
        select(Party.host_id.label("user_id"), Suggestion.party_id)
        .join(Party, Party.id == Suggestion.party_id)
        .where(
            Suggestion.status == SUGGESTION_PENDING,
            Party.status == PARTY_ACTIVE,
            Suggestion.suggested_user_id == me.id,
        )
    )
    both = union_all(host_sees, suggested_sees).subquery()
    # One row per person even if they were suggested for several parties.
    intro = (
        select(both.c.user_id, func.array_agg(both.c.party_id)[1].label("party_id"))
        .group_by(both.c.user_id)
        .subquery()
    )

    shared_count = func.coalesce(shared.c.shared_count, 0)
    stmt = (
        select(User, shared_count, distance.label("distance_km"), intro.c.party_id)
        .outerjoin(shared, shared.c.user_id == User.id)
        .outerjoin(intro, intro.c.user_id == User.id)
        .where(
            or_(shared.c.user_id.is_not(None), intro.c.user_id.is_not(None)),
            User.id.not_in(list(excluded)),
            User.id.not_in(decided),
            User.deleted_at.is_(None),
            User.is_banned.is_(False),
            User.phone_verified_at.is_not(None),
            User.first_name.is_not(None),
            User.latitude.is_not(None),
            distance <= me.search_radius_km,
        )
        .order_by(
            intro.c.party_id.is_(None),  # introductions first
            shared_count.desc(),
            distance.asc(),
        )
        .limit(limit)
        .offset(offset)
    )

    rows = list(await session.execute(stmt))
    if not rows:
        return []

    # One extra query for the shared interests themselves, so the card can show
    # which interests matched rather than just a number.
    candidate_ids = [row[0].id for row in rows]
    shared_rows = await session.execute(
        select(UserInterest.user_id, Interest)
        .join(Interest, Interest.id == UserInterest.interest_id)
        .where(
            UserInterest.user_id.in_(candidate_ids),
            UserInterest.interest_id.in_(my_interest_ids),
        )
    )
    by_user: dict[uuid.UUID, list[Interest]] = {}
    for user_id, interest in shared_rows:
        by_user.setdefault(user_id, []).append(interest)

    return [
        DiscoverCandidate(
            user=user,
            shared_interests=by_user.get(user.id, []),
            distance_km=display_distance_km(float(dist)),
            suggested_for_party_id=party_id,
        )
        for user, _count, dist, party_id in rows
    ]


async def record_decision(
    session: AsyncSession, me: User, target_id: uuid.UUID, decision: str
) -> Match | None:
    """Store a like or pass. Returns the Match if this closed the loop."""
    if target_id == me.id:
        raise RuleError("You cannot like yourself.")
    target = await session.get(User, target_id)
    if target is None or target.deleted_at is not None or target.is_banned:
        raise RuleError("That person is not here any more.", 404)
    if target_id in await blocked_user_ids(session, me.id):
        raise RuleError("That person is not here any more.", 404)

    existing = await session.scalar(
        select(Decision).where(Decision.actor_id == me.id, Decision.target_id == target_id)
    )
    if existing:
        existing.decision = decision
    else:
        session.add(Decision(actor_id=me.id, target_id=target_id, decision=decision))
    await session.flush()

    if decision != DECISION_LIKE:
        return None

    reciprocal = await session.scalar(
        select(Decision).where(
            Decision.actor_id == target_id,
            Decision.target_id == me.id,
            Decision.decision == DECISION_LIKE,
        )
    )
    if not reciprocal:
        return None

    low, high = ordered_pair(me.id, target_id)
    match = await session.scalar(
        select(Match).where(Match.user_low_id == low, Match.user_high_id == high)
    )
    if match:
        return match

    match = Match(user_low_id=low, user_high_id=high)
    session.add(match)

    # An introduction between these two is now fulfilled: the host can invite.
    my_parties = select(Party.id).where(Party.host_id == me.id)
    their_parties = select(Party.id).where(Party.host_id == target_id)
    suggestions = await session.scalars(
        select(Suggestion).where(
            Suggestion.status == SUGGESTION_PENDING,
            or_(
                and_(
                    Suggestion.suggested_user_id == target_id,
                    Suggestion.party_id.in_(my_parties),
                ),
                and_(
                    Suggestion.suggested_user_id == me.id,
                    Suggestion.party_id.in_(their_parties),
                ),
            ),
        )
    )
    for suggestion in suggestions:
        suggestion.status = SUGGESTION_MATCHED

    await session.flush()
    return match


async def are_matched(session: AsyncSession, a: uuid.UUID, b: uuid.UUID) -> bool:
    low, high = ordered_pair(a, b)
    found = await session.scalar(
        select(Match.id).where(Match.user_low_id == low, Match.user_high_id == high)
    )
    return found is not None


async def list_matches(session: AsyncSession, me: User) -> list[tuple[User, datetime]]:
    """Everyone I have matched with, newest first, with 'down to party' surfaced."""
    excluded = await blocked_user_ids(session, me.id)
    stmt = (
        select(User, Match.created_at)
        .join(
            Match,
            or_(
                and_(Match.user_low_id == me.id, Match.user_high_id == User.id),
                and_(Match.user_high_id == me.id, Match.user_low_id == User.id),
            ),
        )
        .where(User.deleted_at.is_(None), User.is_banned.is_(False))
        .order_by(User.down_to_party.desc(), Match.created_at.desc())
    )
    rows = list(await session.execute(stmt))
    return [(user, created) for user, created in rows if user.id not in excluded]


def utcnow() -> datetime:
    return datetime.now(UTC)
