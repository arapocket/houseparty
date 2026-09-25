"""Party rules.

The ones that matter:
  * invite-only, and a host can only invite people they have matched with
  * 20 invites per party unless an admin approved a bigger cap
  * the exact address is withheld until an invite is accepted
  * cancelling a party leaves its chat open
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.errors import RuleError
from app.models import (
    CHAT_PLANNING,
    INVITE_ACCEPTED,
    INVITE_DECLINED,
    INVITE_PENDING,
    INVITE_REVOKED,
    PARTY_ACTIVE,
    PARTY_CANCELLED,
    PARTY_COMPLETED,
    REQUEST_PENDING,
    SUGGESTION_MATCHED,
    SUGGESTION_PENDING,
    Chat,
    Interest,
    Invite,
    InviteCapRequest,
    Party,
    PartyFeedback,
    PartyInterest,
    Suggestion,
    User,
)
from app.services import chat as chat_service
from app.services.interests import get_or_create_interest
from app.services.matching import are_matched, blocked_user_ids


def utcnow() -> datetime:
    return datetime.now(UTC)


async def create_party(
    session: AsyncSession,
    host: User,
    *,
    title: str,
    description: str | None,
    starts_at: datetime,
    ends_at: datetime | None,
    neighborhood: str,
    address: str | None,
    latitude: float | None,
    longitude: float | None,
    interests: list[str],
    source_party_id: uuid.UUID | None = None,
) -> Party:
    if starts_at <= utcnow():
        raise RuleError("A party has to start in the future.")
    if not interests:
        raise RuleError("Give the party at least one interest so people know what it is.")
    if source_party_id is not None:
        source = await session.get(Party, source_party_id)
        if source is None or not await was_there(session, source, host.id):
            raise RuleError("You can only host again for a party you were at.", 403)

    party = Party(
        host_id=host.id,
        title=title,
        description=description,
        starts_at=starts_at,
        ends_at=ends_at,
        neighborhood=neighborhood,
        address=address,
        latitude=latitude if latitude is not None else host.latitude,
        longitude=longitude if longitude is not None else host.longitude,
        guest_cap=host.invite_cap,
        status=PARTY_ACTIVE,
        source_party_id=source_party_id,
    )
    session.add(party)
    await session.flush()

    for raw in interests:
        interest = await get_or_create_interest(session, raw)
        session.add(PartyInterest(party_id=party.id, interest_id=interest.id))

    # The planning chat exists from the start; guests join it when they accept.
    await chat_service.create_chat(session, party, CHAT_PLANNING, host_id=host.id)
    await session.flush()
    return party


async def party_interests(session: AsyncSession, party_id: uuid.UUID) -> list[Interest]:
    rows = await session.scalars(
        select(Interest)
        .join(PartyInterest, PartyInterest.interest_id == Interest.id)
        .where(PartyInterest.party_id == party_id)
    )
    return list(rows)


async def invite_count(session: AsyncSession, party_id: uuid.UUID) -> int:
    """Revoked and declined invites do not count against the cap."""
    return (
        await session.scalar(
            select(func.count())
            .select_from(Invite)
            .where(
                Invite.party_id == party_id,
                Invite.status.in_([INVITE_PENDING, INVITE_ACCEPTED]),
            )
        )
    ) or 0


async def invite(session: AsyncSession, host: User, party: Party, invitee_id: uuid.UUID) -> Invite:
    if party.host_id != host.id:
        raise RuleError("Only the host can invite people.", 403)
    if party.status != PARTY_ACTIVE:
        raise RuleError("This party is not active.")
    if invitee_id == host.id:
        raise RuleError("You are already at your own party.")
    if not await are_matched(session, host.id, invitee_id):
        raise RuleError("You can only invite people you have matched with.", 403)
    if invitee_id in await blocked_user_ids(session, host.id):
        raise RuleError("You cannot invite this person.", 403)

    existing = await session.scalar(
        select(Invite).where(Invite.party_id == party.id, Invite.invitee_id == invitee_id)
    )
    if existing and existing.status in (INVITE_PENDING, INVITE_ACCEPTED):
        return existing

    if await invite_count(session, party.id) >= party.guest_cap:
        raise RuleError(
            f"You have reached the {party.guest_cap}-guest limit. "
            "Request a bigger party to invite more people.",
            409,
        )

    if existing:
        existing.status = INVITE_PENDING
        existing.responded_at = None
        await session.flush()
        return existing

    new_invite = Invite(party_id=party.id, invitee_id=invitee_id, status=INVITE_PENDING)
    session.add(new_invite)
    await session.flush()
    return new_invite


async def respond_to_invite(
    session: AsyncSession, user: User, invite_row: Invite, accept: bool
) -> Invite:
    """Accept or decline. Someone who accepted can still back out later."""
    if invite_row.invitee_id != user.id:
        raise RuleError("That invite is not yours.", 403)
    party = await session.get(Party, invite_row.party_id)
    if party is None or party.status != PARTY_ACTIVE:
        raise RuleError("This party is not happening any more.")

    backing_out = invite_row.status == INVITE_ACCEPTED and not accept
    if invite_row.status != INVITE_PENDING and not backing_out:
        raise RuleError("You have already answered this invite.")

    invite_row.status = INVITE_ACCEPTED if accept else INVITE_DECLINED
    invite_row.responded_at = utcnow()

    chat = await chat_service.get_chat(session, party.id, CHAT_PLANNING)
    if chat is not None:
        if accept:
            await chat_service.add_member(session, chat, user.id)
        else:
            await chat_service.remove_member(session, chat, user.id)

    await session.flush()
    return invite_row


async def revoke_invite(session: AsyncSession, host: User, invite_row: Invite) -> Invite:
    """Hosts can remove anyone they added, before or after acceptance."""
    party = await session.get(Party, invite_row.party_id)
    if party is None or party.host_id != host.id:
        raise RuleError("Only the host can remove a guest.", 403)

    invite_row.status = INVITE_REVOKED
    invite_row.responded_at = utcnow()

    chat = await chat_service.get_chat(session, party.id, CHAT_PLANNING)
    if chat is not None:
        await chat_service.remove_member(session, chat, invite_row.invitee_id)

    await session.flush()
    return invite_row


async def cancel_party(session: AsyncSession, host: User, party: Party) -> Party:
    if party.host_id != host.id:
        raise RuleError("Only the host can cancel.", 403)
    if party.status != PARTY_ACTIVE:
        raise RuleError("This party is already over.")
    party.status = PARTY_CANCELLED
    # Deliberately leaves the chat open so people can sort out what happens next.
    await session.flush()
    return party


async def complete_party(session: AsyncSession, party: Party) -> Chat:
    """Run after the party ends: opens the opt-in reunion chat.

    Nobody is added automatically. Guests who accepted can join it themselves,
    and it stays open forever.
    """
    party.status = PARTY_COMPLETED
    reunion = await chat_service.create_reunion_chat(session, party)
    await session.flush()
    return reunion


async def attendees(session: AsyncSession, party_id: uuid.UUID) -> list[User]:
    rows = await session.scalars(
        select(User)
        .join(Invite, Invite.invitee_id == User.id)
        .where(Invite.party_id == party_id, Invite.status == INVITE_ACCEPTED)
    )
    return list(rows)


async def suggest_guest(
    session: AsyncSession, party: Party, suggester: User, suggested_user_id: uuid.UUID
) -> Suggestion:
    """A guest pointing the host at someone.

    The host still can only invite their own matches, so this creates an
    introduction: both people surface at the top of each other's Discover.
    """
    if party.status != PARTY_ACTIVE:
        raise RuleError("This party is not active.")
    if suggested_user_id in (party.host_id, suggester.id):
        raise RuleError("Suggest somebody else.")
    suggested = await session.get(User, suggested_user_id)
    if suggested is None or suggested.deleted_at is not None or suggested.is_banned:
        raise RuleError("That person is not here any more.", 404)

    is_guest = await session.scalar(
        select(Invite.id).where(
            Invite.party_id == party.id,
            Invite.invitee_id == suggester.id,
            Invite.status == INVITE_ACCEPTED,
        )
    )
    if not is_guest and party.host_id != suggester.id:
        raise RuleError("Only people going to the party can suggest guests.", 403)

    existing = await session.scalar(
        select(Suggestion).where(
            Suggestion.party_id == party.id,
            Suggestion.suggested_user_id == suggested_user_id,
        )
    )
    if existing:
        return existing

    # If the host already matched with them there is nothing to introduce.
    already = await are_matched(session, party.host_id, suggested_user_id)
    suggestion = Suggestion(
        party_id=party.id,
        suggested_by_id=suggester.id,
        suggested_user_id=suggested_user_id,
        status=SUGGESTION_MATCHED if already else SUGGESTION_PENDING,
    )
    session.add(suggestion)
    await session.flush()
    return suggestion


async def was_there(session: AsyncSession, party: Party, user_id: uuid.UUID) -> bool:
    """Hosted it, or accepted an invite to it."""
    if party.host_id == user_id:
        return True
    found = await session.scalar(
        select(Invite.id).where(
            Invite.party_id == party.id,
            Invite.invitee_id == user_id,
            Invite.status == INVITE_ACCEPTED,
        )
    )
    return found is not None


async def get_visible_party(session: AsyncSession, party_id: uuid.UUID, user: User) -> Party:
    """Parties are invite-only, so only the host and invitees can see one.

    Anyone else gets a 404 rather than a 403, so the API does not even confirm
    the party exists.
    """
    party = await session.get(Party, party_id)
    if party is None:
        raise RuleError("Party not found.", 404)
    if party.host_id == user.id:
        return party
    my_invite = await session.scalar(
        select(Invite).where(Invite.party_id == party.id, Invite.invitee_id == user.id)
    )
    if my_invite is None or my_invite.status == INVITE_REVOKED:
        raise RuleError("Party not found.", 404)
    return party


async def get_hosted_party(session: AsyncSession, party_id: uuid.UUID, host: User) -> Party:
    party = await get_visible_party(session, party_id, host)
    if party.host_id != host.id:
        raise RuleError("Only the host can do that.", 403)
    return party


async def update_party(session: AsyncSession, host: User, party: Party, changes: dict) -> Party:
    if party.status != PARTY_ACTIVE:
        raise RuleError("This party is over, so it can't be edited.")
    starts_at = changes.get("starts_at", party.starts_at)
    ends_at = changes.get("ends_at", party.ends_at)
    if "starts_at" in changes and starts_at <= utcnow():
        raise RuleError("A party has to start in the future.")
    if ends_at is not None and ends_at <= starts_at:
        raise RuleError("The party has to end after it starts.")
    for field, value in changes.items():
        setattr(party, field, value)
    await session.flush()
    return party


async def my_parties(session: AsyncSession, user: User) -> list[Party]:
    """Parties I am hosting or invited to (not revoked), soonest first."""
    invited = select(Invite.party_id).where(
        Invite.invitee_id == user.id,
        Invite.status.in_([INVITE_PENDING, INVITE_ACCEPTED]),
    )
    rows = await session.scalars(
        select(Party)
        .where((Party.host_id == user.id) | Party.id.in_(invited))
        .order_by(Party.starts_at)
    )
    return list(rows)


async def guest_list(session: AsyncSession, party: Party) -> list[tuple[Invite, User]]:
    """Everyone the host has invited, with where each invite stands."""
    rows = await session.execute(
        select(Invite, User)
        .join(User, User.id == Invite.invitee_id)
        .where(Invite.party_id == party.id, Invite.status != INVITE_REVOKED)
        .order_by(Invite.created_at)
    )
    return [(invite_row, user) for invite_row, user in rows]


def end_time(party: Party) -> datetime:
    if party.ends_at is not None:
        return party.ends_at
    return party.starts_at + timedelta(hours=settings.default_party_length_hours)


async def complete_finished_parties(session: AsyncSession) -> list[Party]:
    """Called by the background job in main.py every few minutes."""
    now = utcnow()
    # Rough filter in SQL, exact check in Python: parties with no end time
    # finish a fixed number of hours after they start.
    candidates = await session.scalars(
        select(Party).where(
            Party.status == PARTY_ACTIVE,
            Party.starts_at <= now,
        )
    )
    finished = [party for party in candidates if end_time(party) <= now]
    for party in finished:
        await complete_party(session, party)
    return finished


async def leave_feedback(
    session: AsyncSession,
    author: User,
    party: Party,
    subject_id: uuid.UUID,
    would_party_again: bool,
    note: str | None,
) -> None:
    if party.status != PARTY_COMPLETED:
        raise RuleError("You can leave feedback once the party is over.")
    if subject_id == author.id:
        raise RuleError("Pick someone other than yourself.")
    if not await was_there(session, party, author.id):
        raise RuleError("Only people who were there can leave feedback.", 403)
    if not await was_there(session, party, subject_id):
        raise RuleError("They weren't at this party.", 404)

    existing = await session.scalar(
        select(PartyFeedback).where(
            PartyFeedback.party_id == party.id,
            PartyFeedback.author_id == author.id,
            PartyFeedback.subject_id == subject_id,
        )
    )
    if existing:
        existing.would_party_again = would_party_again
        existing.note = note
    else:
        session.add(
            PartyFeedback(
                party_id=party.id,
                author_id=author.id,
                subject_id=subject_id,
                would_party_again=would_party_again,
                note=note,
            )
        )
    await session.flush()


async def request_bigger_party(
    session: AsyncSession, host: User, party: Party | None, requested_cap: int, reason: str | None
) -> InviteCapRequest:
    if requested_cap <= host.invite_cap:
        raise RuleError(f"You can already invite {host.invite_cap} people.")

    request = InviteCapRequest(
        host_id=host.id,
        party_id=party.id if party else None,
        requested_cap=requested_cap,
        reason=reason,
        status=REQUEST_PENDING,
    )
    session.add(request)
    await session.flush()
    return request
