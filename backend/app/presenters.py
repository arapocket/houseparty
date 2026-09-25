"""Turning database rows into the shapes the app sees.

One place decides what is public, which is how the exact address and location
stay server-side by default instead of by accident.
"""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.errors import RuleError
from app.models import (
    CHAT_REUNION,
    INVITE_ACCEPTED,
    INVITE_PENDING,
    Chat,
    ChatMember,
    Invite,
    Message,
    Party,
    User,
)
from app.schemas import ChatOut, MeOut, MessageOut, PartyOut, PublicProfileOut
from app.services.geo import display_distance_km, haversine_km
from app.services.matching import age_on


def _distance(viewer: User, party: Party) -> int | None:
    """Rounded to a whole km. Never the exact spot."""
    if viewer.latitude is None or viewer.longitude is None:
        return None
    if party.latitude is None or party.longitude is None:
        return None
    km = haversine_km(viewer.latitude, viewer.longitude, party.latitude, party.longitude)
    return display_distance_km(km)


def interest_names(user: User) -> list[str]:
    ordered = sorted(user.interests, key=lambda ui: ui.position)
    return [ui.interest.display for ui in ordered]


def shared_interests(me: User, other: User) -> list[str]:
    """What two people have in common, in the order *I* listed my interests,
    so the same things always show up in the same order on my screens."""
    theirs = {ui.interest_id for ui in other.interests}
    mine = sorted(me.interests, key=lambda ui: ui.position)
    return [ui.interest.display for ui in mine if ui.interest_id in theirs]


def public_profile(user: User) -> PublicProfileOut:
    return PublicProfileOut(
        id=user.id,
        first_name=user.first_name,
        age=age_on(user.birthdate) if user.birthdate else None,
        bio=user.bio,
        photo_url=user.photo_url,
        neighborhood=user.neighborhood,
        down_to_party=user.down_to_party,
        interests=interest_names(user),
    )


def me(user: User) -> MeOut:
    base = public_profile(user)
    return MeOut(
        **base.model_dump(),
        phone=user.phone,
        search_radius_km=user.search_radius_km,
        invite_cap=user.invite_cap,
        needs_onboarding=not user.is_onboarded,
        photo_in_review=user.pending_photo_url is not None,
    )


async def party_out(
    session: AsyncSession,
    party: Party,
    viewer: User,
    *,
    include_guests: bool = True,
) -> PartyOut:
    from app.services.parties import party_interests

    viewer_id = viewer.id
    host = await session.get(User, party.host_id)
    if host is None:
        raise RuleError("Party not found.", 404)
    is_host = party.host_id == viewer_id

    my_invite = await session.scalar(
        select(Invite).where(Invite.party_id == party.id, Invite.invitee_id == viewer_id)
    )
    accepted = is_host or (my_invite is not None and my_invite.status == INVITE_ACCEPTED)

    guest_count = (
        await session.scalar(
            select(func.count())
            .select_from(Invite)
            .where(Invite.party_id == party.id, Invite.status == INVITE_ACCEPTED)
        )
    ) or 0
    held = (
        await session.scalar(
            select(func.count())
            .select_from(Invite)
            .where(
                Invite.party_id == party.id,
                Invite.status.in_([INVITE_PENDING, INVITE_ACCEPTED]),
            )
        )
    ) or 0

    guests: list[PublicProfileOut] = []
    if include_guests and (accepted or my_invite is not None):
        # Invitees can see who else is going before they answer.
        rows = await session.scalars(
            select(User)
            .join(Invite, Invite.invitee_id == User.id)
            .where(Invite.party_id == party.id, Invite.status == INVITE_ACCEPTED)
        )
        guests = [public_profile(guest) for guest in rows]

    return PartyOut(
        id=party.id,
        title=party.title,
        description=party.description,
        starts_at=party.starts_at,
        ends_at=party.ends_at,
        neighborhood=party.neighborhood,
        status=party.status,
        interests=[i.display for i in await party_interests(session, party.id)],
        host=public_profile(host),
        guest_count=guest_count,
        guest_cap=party.guest_cap,
        invites_left=max(0, party.guest_cap - held),
        distance_km=_distance(viewer, party),
        address=party.address if accepted else None,
        my_invite_status=my_invite.status if my_invite else ("host" if is_host else None),
        guests=guests,
        latitude=party.latitude if is_host else None,
        longitude=party.longitude if is_host else None,
    )


async def messages_out(session: AsyncSession, messages: list[Message]) -> list[MessageOut]:
    sender_ids = {m.sender_id for m in messages if m.sender_id is not None}
    names: dict[uuid.UUID, str | None] = {}
    if sender_ids:
        rows = await session.execute(
            select(User.id, User.first_name).where(User.id.in_(sender_ids))
        )
        names = {user_id: name for user_id, name in rows}
    return [
        MessageOut(
            id=m.id,
            chat_id=m.chat_id,
            sender_id=m.sender_id,
            sender_name=names.get(m.sender_id) if m.sender_id else None,
            body=m.body,
            created_at=m.created_at,
        )
        for m in messages
    ]


async def chat_out(
    session: AsyncSession, chat: Chat, joined: bool, hidden_senders: set[uuid.UUID] | None = None
) -> ChatOut:
    from app.services.chat import last_message

    member_count = (
        await session.scalar(
            select(func.count())
            .select_from(ChatMember)
            .where(ChatMember.chat_id == chat.id, ChatMember.left_at.is_(None))
        )
    ) or 0
    # Only show a preview to people in the chat.
    latest = await last_message(session, chat.id, hidden_senders or set()) if joined else None
    sender = await session.get(User, latest.sender_id) if latest and latest.sender_id else None
    return ChatOut(
        id=chat.id,
        party_id=chat.party_id,
        kind=chat.kind,
        title=chat.title,
        member_count=member_count,
        joined=joined,
        # Only reunion chats are opt-in. chats_for() already hides reunion
        # chats from anyone voted out, so not joined means they may join.
        can_join=(chat.kind == CHAT_REUNION and not joined),
        last_message=latest.body if latest else None,
        last_message_at=latest.created_at if latest else None,
        last_sender_name=sender.first_name if sender else None,
    )
