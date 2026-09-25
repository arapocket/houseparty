"""Invites you have received."""

import uuid

from fastapi import APIRouter
from sqlalchemy import select

from app import presenters
from app.deps import OnboardedUser, Session
from app.errors import RuleError
from app.models import INVITE_ACCEPTED, INVITE_PENDING, Invite, Party
from app.schemas import InviteOut, InviteRespondIn
from app.services import parties

router = APIRouter(prefix="/invites", tags=["invites"])


@router.get("")
async def my_invites(user: OnboardedUser, session: Session) -> list[InviteOut]:
    """Invites waiting for an answer or already accepted, soonest party first."""
    rows = await session.execute(
        select(Invite, Party)
        .join(Party, Party.id == Invite.party_id)
        .where(
            Invite.invitee_id == user.id,
            Invite.status.in_([INVITE_PENDING, INVITE_ACCEPTED]),
        )
        .order_by(Party.starts_at)
    )
    return [
        InviteOut(
            id=invite.id,
            party_id=invite.party_id,
            status=invite.status,
            created_at=invite.created_at,
            party=await presenters.party_out(session, party, user),
        )
        for invite, party in rows
    ]


@router.post("/{invite_id}/respond")
async def respond(
    invite_id: uuid.UUID, data: InviteRespondIn, user: OnboardedUser, session: Session
) -> InviteOut:
    row = await session.get(Invite, invite_id)
    if row is None or row.invitee_id != user.id:
        raise RuleError("Invite not found.", 404)
    await parties.respond_to_invite(session, user, row, data.accept)
    party = await parties.get_visible_party(session, row.party_id, user)
    return InviteOut(
        id=row.id,
        party_id=row.party_id,
        status=row.status,
        created_at=row.created_at,
        party=await presenters.party_out(session, party, user),
    )
