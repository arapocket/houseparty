"""Reports and blocks.

Reports go to the admin page (/admin) for a person to look at. Blocks take
effect immediately and cut both ways: neither person sees the other in
Discover, matches, or invites again.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.errors import RuleError
from app.models import (
    INVITE_PENDING,
    INVITE_REVOKED,
    Block,
    Invite,
    Message,
    Party,
    Report,
    User,
)
from app.schemas import ReportIn


async def report(session: AsyncSession, reporter: User, data: ReportIn) -> Report:
    subjects = [data.subject_user_id, data.subject_party_id, data.subject_message_id]
    if not any(subjects):
        raise RuleError("Say who or what you are reporting.")

    # Check each thing exists, so the admin page never shows a dead link.
    if data.subject_user_id and await session.get(User, data.subject_user_id) is None:
        raise RuleError("That person was not found.", 404)
    if data.subject_party_id and await session.get(Party, data.subject_party_id) is None:
        raise RuleError("That party was not found.", 404)
    if data.subject_message_id and await session.get(Message, data.subject_message_id) is None:
        raise RuleError("That message was not found.", 404)

    row = Report(
        reporter_id=reporter.id,
        subject_user_id=data.subject_user_id,
        subject_party_id=data.subject_party_id,
        subject_message_id=data.subject_message_id,
        reason=data.reason,
        note=data.note,
    )
    session.add(row)
    await session.flush()
    return row


async def block(session: AsyncSession, blocker: User, blocked_id: uuid.UUID) -> None:
    if blocked_id == blocker.id:
        raise RuleError("You can't block yourself.")
    if await session.get(User, blocked_id) is None:
        raise RuleError("That person was not found.", 404)

    existing = await session.scalar(
        select(Block).where(Block.blocker_id == blocker.id, Block.blocked_id == blocked_id)
    )
    if existing is None:
        session.add(Block(blocker_id=blocker.id, blocked_id=blocked_id))

    # Unanswered invites between the two, in either direction, are withdrawn.
    for host_id, guest_id in ((blocker.id, blocked_id), (blocked_id, blocker.id)):
        hosted = select(Party.id).where(Party.host_id == host_id)
        await session.execute(
            update(Invite)
            .where(
                Invite.party_id.in_(hosted),
                Invite.invitee_id == guest_id,
                Invite.status == INVITE_PENDING,
            )
            .values(status=INVITE_REVOKED)
        )
    await session.flush()
