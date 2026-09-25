"""Parties. Always invite-only: there is no way to browse or find one.

You see a party only if you host it or were invited to it.
"""

import uuid

from fastapi import APIRouter, status

from app import presenters
from app.deps import OnboardedUser, Session
from app.errors import RuleError
from app.models import CHAT_PLANNING, Invite
from app.schemas import (
    BiggerPartyIn,
    FeedbackIn,
    GuestOut,
    InviteIn,
    InviteOut,
    PartyIn,
    PartyOut,
    PartyUpdateIn,
    SimpleOk,
    SuggestGuestIn,
)
from app.services import chat as chat_service
from app.services import parties

router = APIRouter(prefix="/parties", tags=["parties"])


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_party(data: PartyIn, user: OnboardedUser, session: Session) -> PartyOut:
    party = await parties.create_party(session, user, **data.model_dump())
    return await presenters.party_out(session, party, user)


@router.get("")
async def my_parties(user: OnboardedUser, session: Session) -> list[PartyOut]:
    rows = await parties.my_parties(session, user)
    return [await presenters.party_out(session, p, user, include_guests=False) for p in rows]


@router.get("/{party_id}")
async def get_party(party_id: uuid.UUID, user: OnboardedUser, session: Session) -> PartyOut:
    party = await parties.get_visible_party(session, party_id, user)
    return await presenters.party_out(session, party, user)


@router.patch("/{party_id}")
async def update_party(
    party_id: uuid.UUID, data: PartyUpdateIn, user: OnboardedUser, session: Session
) -> PartyOut:
    party = await parties.get_hosted_party(session, party_id, user)
    await parties.update_party(session, user, party, data.model_dump(exclude_unset=True))
    return await presenters.party_out(session, party, user)


@router.post("/{party_id}/cancel")
async def cancel_party(party_id: uuid.UUID, user: OnboardedUser, session: Session) -> PartyOut:
    party = await parties.get_hosted_party(session, party_id, user)
    await parties.cancel_party(session, user, party)
    return await presenters.party_out(session, party, user)


@router.get("/{party_id}/guests")
async def guest_list(party_id: uuid.UUID, user: OnboardedUser, session: Session) -> list[GuestOut]:
    """The host's view: everyone invited and whether they said yes."""
    party = await parties.get_hosted_party(session, party_id, user)
    return [
        GuestOut(invite_id=invite.id, user=presenters.public_profile(guest), status=invite.status)
        for invite, guest in await parties.guest_list(session, party)
    ]


@router.post("/{party_id}/invites", status_code=status.HTTP_201_CREATED)
async def invite(
    party_id: uuid.UUID, data: InviteIn, user: OnboardedUser, session: Session
) -> InviteOut:
    party = await parties.get_hosted_party(session, party_id, user)
    row = await parties.invite(session, user, party, data.user_id)
    return InviteOut(id=row.id, party_id=row.party_id, status=row.status, created_at=row.created_at)


@router.delete("/{party_id}/invites/{invite_id}")
async def remove_guest(
    party_id: uuid.UUID, invite_id: uuid.UUID, user: OnboardedUser, session: Session
) -> SimpleOk:
    party = await parties.get_hosted_party(session, party_id, user)
    row = await session.get(Invite, invite_id)
    if row is None or row.party_id != party.id:
        raise RuleError("Invite not found.", 404)
    await parties.revoke_invite(session, user, row)
    await session.commit()
    planning = await chat_service.get_chat(session, party.id, CHAT_PLANNING)
    if planning is not None:
        await chat_service.manager.disconnect_user(planning.id, row.invitee_id)
    return SimpleOk()


@router.post("/{party_id}/suggestions", status_code=status.HTTP_201_CREATED)
async def suggest_guest(
    party_id: uuid.UUID, data: SuggestGuestIn, user: OnboardedUser, session: Session
) -> SimpleOk:
    party = await parties.get_visible_party(session, party_id, user)
    await parties.suggest_guest(session, party, user, data.user_id)
    return SimpleOk()


@router.post("/{party_id}/bigger", status_code=status.HTTP_201_CREATED)
async def request_bigger(
    party_id: uuid.UUID, data: BiggerPartyIn, user: OnboardedUser, session: Session
) -> SimpleOk:
    """Ask an admin to raise the 20-guest limit."""
    party = await parties.get_hosted_party(session, party_id, user)
    await parties.request_bigger_party(session, user, party, data.requested_cap, data.reason)
    return SimpleOk()


@router.post("/{party_id}/feedback")
async def leave_feedback(
    party_id: uuid.UUID, data: FeedbackIn, user: OnboardedUser, session: Session
) -> SimpleOk:
    """ "Would you party with them again?" Private; nobody sees the answers."""
    party = await parties.get_visible_party(session, party_id, user)
    await parties.leave_feedback(
        session, user, party, data.user_id, data.would_party_again, data.note
    )
    return SimpleOk()
