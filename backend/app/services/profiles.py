"""Your own profile: editing it, setting your interests, deleting it."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.errors import RuleError
from app.models import (
    INVITE_DECLINED,
    INVITE_PENDING,
    PARTY_ACTIVE,
    PARTY_CANCELLED,
    DeviceToken,
    Invite,
    Party,
    User,
    UserInterest,
)
from app.schemas import ProfileIn
from app.services import interests as interest_service
from app.services.matching import blocked_user_ids, meets_minimum_age


def utcnow() -> datetime:
    return datetime.now(UTC)


async def update_profile(session: AsyncSession, user: User, data: ProfileIn) -> User:
    # exclude_unset: only the fields the app actually sent. A field sent as
    # null is included (and clears the value); a field left out is untouched.
    changes = data.model_dump(exclude_unset=True)

    if "birthdate" in changes:
        birthdate = changes.pop("birthdate")
        if user.birthdate is not None and birthdate != user.birthdate:
            raise RuleError("Your birthdate can't be changed.")
        if birthdate is None or not meets_minimum_age(birthdate):
            raise RuleError(f"House Party is for people {settings.min_age} and over.", 403)
        user.birthdate = birthdate

    if "first_name" in changes and not changes["first_name"]:
        raise RuleError("Your first name can't be empty.")

    if "search_radius_km" in changes and changes["search_radius_km"] is None:
        changes.pop("search_radius_km")
    if "down_to_party" in changes and changes["down_to_party"] is None:
        changes.pop("down_to_party")

    for field, value in changes.items():
        setattr(user, field, value)

    await session.flush()
    return user


async def set_interests(session: AsyncSession, user: User, raw_list: list[str]) -> User:
    """Replace the whole list. The order they send is the order we show."""

    # Two spellings of the same thing ("Radiohead", "radiohead!") count once.
    wanted: list[str] = []
    seen: set[str] = set()
    for raw in raw_list:
        normalized = interest_service.normalize_interest(raw)
        if not interest_service.is_acceptable(normalized):
            raise RuleError(f'"{raw.strip()}" can\'t be used as an interest.')
        if normalized not in seen:
            seen.add(normalized)
            wanted.append(raw)

    if len(wanted) > settings.max_interests_per_user:
        raise RuleError(f"You can have up to {settings.max_interests_per_user} interests.")

    current = {ui.interest_id: ui for ui in user.interests}
    touched = set(current)

    keep_ids = set()
    for position, raw in enumerate(wanted):
        interest = await interest_service.get_or_create_interest(session, raw)
        keep_ids.add(interest.id)
        touched.add(interest.id)
        if interest.id in current:
            current[interest.id].position = position
        else:
            user.interests.append(
                UserInterest(user_id=user.id, interest=interest, position=position)
            )

    for interest_id, ui in current.items():
        if interest_id not in keep_ids:
            user.interests.remove(ui)  # the relationship deletes the row

    await session.flush()
    for interest_id in touched:
        await interest_service.recount(session, interest_id)
    await session.flush()
    return user


async def delete_account(session: AsyncSession, user: User) -> None:
    """Required by the App Store. We keep the row (messages and reports point
    at it) but strip everything that identifies the person."""
    interest_ids = [ui.interest_id for ui in user.interests]
    user.interests.clear()

    # Their upcoming parties are off, and invites they had not answered go away.
    await session.execute(
        update(Party)
        .where(Party.host_id == user.id, Party.status == PARTY_ACTIVE)
        .values(status=PARTY_CANCELLED)
    )
    await session.execute(
        update(Invite)
        .where(Invite.invitee_id == user.id, Invite.status == INVITE_PENDING)
        .values(status=INVITE_DECLINED, responded_at=utcnow())
    )

    # No more notifications to their phones.
    await session.execute(delete(DeviceToken).where(DeviceToken.user_id == user.id))

    # The phone column is unique, so free the number up for a fresh signup.
    user.phone = f"deleted:{user.id}"
    user.first_name = None
    user.bio = None
    user.photo_url = None
    user.pending_photo_url = None
    user.pending_photo_reason = None
    user.neighborhood = None
    user.latitude = None
    user.longitude = None
    user.down_to_party = False
    user.deleted_at = utcnow()

    await session.flush()
    for interest_id in interest_ids:
        await interest_service.recount(session, interest_id)


async def get_visible_user(session: AsyncSession, viewer: User, user_id: uuid.UUID) -> User:
    """Someone else's profile, unless they are gone or either side blocked."""
    other = await session.scalar(
        select(User).where(User.id == user_id, User.deleted_at.is_(None), User.is_banned.is_(False))
    )
    if other is None or other.id in await blocked_user_ids(session, viewer.id):
        raise RuleError("That person is not here any more.", 404)
    return other
