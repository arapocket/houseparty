"""Chats.

Two kinds, with deliberately different politics:

  planning  the host's chat for a specific party. The host adds people (by
            inviting them) and can remove anyone they added.
  reunion   opens after the party, opt-in, and never closes. No host powers
            here: members vote people out, and the host can be voted out of
            the chat they started.
"""

from __future__ import annotations

import contextlib
import uuid
from datetime import UTC, datetime

from fastapi import WebSocket
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.errors import RuleError
from app.models import (
    CHAT_PLANNING,
    CHAT_REUNION,
    INVITE_ACCEPTED,
    Chat,
    ChatMember,
    Invite,
    KickVote,
    Message,
    Party,
)


def utcnow() -> datetime:
    return datetime.now(UTC)


def votes_needed(active_members_excluding_target: int) -> int:
    """A simple majority of everyone who could vote.

    3 voters -> 2, 4 -> 3, 5 -> 3. With fewer than two other people there is
    nobody to outvote, so kicking is off.
    """
    if active_members_excluding_target < 2:
        return 0
    return active_members_excluding_target // 2 + 1


async def create_chat(
    session: AsyncSession, party: Party, kind: str, host_id: uuid.UUID | None = None
) -> Chat:
    chat = Chat(party_id=party.id, kind=kind, title=party.title)
    session.add(chat)
    await session.flush()
    if host_id is not None:
        session.add(ChatMember(chat_id=chat.id, user_id=host_id, is_host=(kind == CHAT_PLANNING)))
        await session.flush()
    return chat


async def get_chat(session: AsyncSession, party_id: uuid.UUID, kind: str) -> Chat | None:
    return await session.scalar(select(Chat).where(Chat.party_id == party_id, Chat.kind == kind))


async def create_reunion_chat(session: AsyncSession, party: Party) -> Chat:
    """Opt-in group for everyone who was there. Empty until people join."""
    existing = await get_chat(session, party.id, CHAT_REUNION)
    if existing:
        return existing
    chat = Chat(party_id=party.id, kind=CHAT_REUNION, title=party.title)
    session.add(chat)
    await session.flush()
    return chat


async def eligible_for_reunion(session: AsyncSession, chat: Chat, user_id: uuid.UUID) -> bool:
    """You may join a reunion chat if you hosted or accepted an invite."""
    party = await session.get(Party, chat.party_id)
    if party is None:
        return False
    if party.host_id == user_id:
        return True
    attended = await session.scalar(
        select(Invite.id).where(
            Invite.party_id == party.id,
            Invite.invitee_id == user_id,
            Invite.status == INVITE_ACCEPTED,
        )
    )
    return attended is not None


async def add_member(
    session: AsyncSession, chat: Chat, user_id: uuid.UUID, is_host: bool = False
) -> ChatMember:
    member = await session.scalar(
        select(ChatMember).where(ChatMember.chat_id == chat.id, ChatMember.user_id == user_id)
    )
    if member:
        # Someone voted out does not get re-added by accepting another invite.
        if member.removed_by_vote:
            return member
        member.left_at = None
        await session.flush()
        return member

    member = ChatMember(chat_id=chat.id, user_id=user_id, is_host=is_host)
    session.add(member)
    await session.flush()
    return member


async def remove_member(session: AsyncSession, chat: Chat, user_id: uuid.UUID) -> None:
    member = await session.scalar(
        select(ChatMember).where(
            ChatMember.chat_id == chat.id,
            ChatMember.user_id == user_id,
            ChatMember.left_at.is_(None),
        )
    )
    if member:
        member.left_at = utcnow()
        await session.flush()


async def active_members(session: AsyncSession, chat_id: uuid.UUID) -> list[ChatMember]:
    rows = await session.scalars(
        select(ChatMember).where(ChatMember.chat_id == chat_id, ChatMember.left_at.is_(None))
    )
    return list(rows)


async def is_member(session: AsyncSession, chat_id: uuid.UUID, user_id: uuid.UUID) -> bool:
    found = await session.scalar(
        select(ChatMember.id).where(
            ChatMember.chat_id == chat_id,
            ChatMember.user_id == user_id,
            ChatMember.left_at.is_(None),
        )
    )
    return found is not None


async def post_message(
    session: AsyncSession, chat: Chat, sender_id: uuid.UUID, body: str
) -> Message:
    if not await is_member(session, chat.id, sender_id):
        raise RuleError("You are not in this chat.", 403)
    body = body.strip()
    if not body:
        raise RuleError("Say something first.")
    message = Message(chat_id=chat.id, sender_id=sender_id, body=body[:2000])
    session.add(message)
    await session.flush()
    return message


async def history(
    session: AsyncSession, chat_id: uuid.UUID, before: datetime | None = None, limit: int = 50
) -> list[Message]:
    stmt = select(Message).where(Message.chat_id == chat_id, Message.deleted_at.is_(None))
    if before:
        stmt = stmt.where(Message.created_at < before)
    stmt = stmt.order_by(Message.created_at.desc()).limit(limit)
    rows = list(await session.scalars(stmt))
    return list(reversed(rows))


async def cast_kick_vote(
    session: AsyncSession, chat: Chat, voter_id: uuid.UUID, target_id: uuid.UUID
) -> tuple[int, int, bool]:
    """Vote to remove someone from a reunion chat.

    Returns (votes so far, votes needed, whether they were removed).
    """
    if chat.kind != CHAT_REUNION:
        raise RuleError("Voting only happens in reunion chats.")
    if voter_id == target_id:
        raise RuleError("To remove yourself, leave the chat.")
    if not await is_member(session, chat.id, voter_id):
        raise RuleError("You are not in this chat.", 403)
    if not await is_member(session, chat.id, target_id):
        raise RuleError("They are not in this chat.", 404)

    existing = await session.scalar(
        select(KickVote).where(
            KickVote.chat_id == chat.id,
            KickVote.target_id == target_id,
            KickVote.voter_id == voter_id,
        )
    )
    if not existing:
        session.add(KickVote(chat_id=chat.id, target_id=target_id, voter_id=voter_id))
        await session.flush()

    members = await active_members(session, chat.id)
    voters = [m.user_id for m in members if m.user_id != target_id]
    needed = votes_needed(len(voters))

    # Only count votes from people still in the chat; someone who voted and
    # then left should not keep counting.
    votes = (
        await session.scalar(
            select(func.count())
            .select_from(KickVote)
            .where(
                KickVote.chat_id == chat.id,
                KickVote.target_id == target_id,
                KickVote.voter_id.in_(voters),
            )
        )
    ) or 0

    if needed and votes >= needed:
        member = next((m for m in members if m.user_id == target_id), None)
        if member:
            member.left_at = utcnow()
            member.removed_by_vote = True
        await session.execute(
            delete(KickVote).where(KickVote.chat_id == chat.id, KickVote.target_id == target_id)
        )
        await session.flush()
        return votes, needed, True

    return votes, needed, False


async def get_chat_for_member(
    session: AsyncSession, chat_id: uuid.UUID, user_id: uuid.UUID
) -> Chat:
    chat = await session.get(Chat, chat_id)
    if chat is None or not await is_member(session, chat.id, user_id):
        raise RuleError("Chat not found.", 404)
    return chat


async def chats_for(session: AsyncSession, user_id: uuid.UUID) -> list[tuple[Chat, bool]]:
    """Chats to show in someone's list, each with whether they are in it.

    That is every chat they are an active member of, plus reunion chats for
    parties they were at that they have not joined yet (so the app can offer
    a "join" button). Anyone voted out of a reunion chat does not see it again.
    """
    mine = await session.execute(
        select(ChatMember.chat_id, ChatMember.left_at, ChatMember.removed_by_vote).where(
            ChatMember.user_id == user_id
        )
    )
    active_ids: set[uuid.UUID] = set()
    gone_ids: set[uuid.UUID] = set()
    for chat_id, left_at, removed in mine:
        if left_at is None:
            active_ids.add(chat_id)
        elif removed:
            gone_ids.add(chat_id)

    attended = (
        select(Invite.party_id)
        .where(Invite.invitee_id == user_id, Invite.status == INVITE_ACCEPTED)
        .union(select(Party.id).where(Party.host_id == user_id))
    )
    reunions = await session.scalars(
        select(Chat).where(Chat.kind == CHAT_REUNION, Chat.party_id.in_(attended))
    )
    joined = await session.scalars(select(Chat).where(Chat.id.in_(active_ids)))

    out: dict[uuid.UUID, tuple[Chat, bool]] = {}
    for chat in joined:
        out[chat.id] = (chat, True)
    for chat in reunions:
        if chat.id not in out and chat.id not in gone_ids:
            out[chat.id] = (chat, False)
    return sorted(out.values(), key=lambda pair: pair[0].created_at, reverse=True)


async def join_reunion(session: AsyncSession, chat: Chat, user_id: uuid.UUID) -> None:
    if chat.kind != CHAT_REUNION:
        raise RuleError("The host adds people to the planning chat.", 403)
    if not await eligible_for_reunion(session, chat, user_id):
        raise RuleError("Only people who were at the party can join.", 403)
    member = await add_member(session, chat, user_id)
    if member.removed_by_vote:
        raise RuleError("The group voted you out of this chat.", 403)


async def leave(session: AsyncSession, chat: Chat, user_id: uuid.UUID) -> None:
    if chat.kind == CHAT_PLANNING:
        party = await session.get(Party, chat.party_id)
        if party is not None and party.host_id == user_id:
            raise RuleError("You're the host, so you can't leave the planning chat.")
    await remove_member(session, chat, user_id)


class ConnectionManager:
    """Who is connected to which chat, for live delivery.

    In memory, so it works for one server process. Running more than one
    process means messages only reach the clients on the same process; the fix
    is Redis pub/sub, and it can wait until there is a second process.

    Each open connection is remembered along with whose it is, so when
    someone is removed from a chat we can hang up on them.
    """

    def __init__(self) -> None:
        # chat id -> {websocket: user id}
        self._rooms: dict[uuid.UUID, dict[WebSocket, uuid.UUID]] = {}

    def join(self, chat_id: uuid.UUID, user_id: uuid.UUID, websocket: WebSocket) -> None:
        self._rooms.setdefault(chat_id, {})[websocket] = user_id

    def leave(self, chat_id: uuid.UUID, websocket: WebSocket) -> None:
        room = self._rooms.get(chat_id)
        if room is None:
            return
        room.pop(websocket, None)
        if not room:
            self._rooms.pop(chat_id, None)

    async def broadcast(self, chat_id: uuid.UUID, payload: dict) -> None:
        for websocket in list(self._rooms.get(chat_id, {})):
            try:
                await websocket.send_json(payload)
            except Exception:
                self.leave(chat_id, websocket)

    async def disconnect_user(self, chat_id: uuid.UUID, user_id: uuid.UUID) -> None:
        room = self._rooms.get(chat_id, {})
        for websocket, owner in list(room.items()):
            if owner == user_id:
                self.leave(chat_id, websocket)
                # 4403 is our own code meaning "you were removed from this chat".
                with contextlib.suppress(Exception):
                    await websocket.close(code=4403)


manager = ConnectionManager()
