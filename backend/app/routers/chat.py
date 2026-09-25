"""Chats: the host's planning chat, and the opt-in reunion chat afterwards.

Messages go out live over a WebSocket. Sending works either way: POST a
message, or send {"body": "..."} down the open socket. Everyone connected
gets {"type": "message", "message": {...}}.
"""

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, WebSocket, WebSocketDisconnect, status
from sqlalchemy import select

from app import presenters
from app.db import SessionFactory
from app.deps import OnboardedUser, Session, user_from_token
from app.errors import RuleError
from app.models import Chat, ChatMember, User
from app.schemas import (
    ChatMemberOut,
    ChatOut,
    KickVoteIn,
    KickVoteOut,
    MessageIn,
    MessageOut,
    SimpleOk,
)
from app.services import chat as chat_service
from app.services.chat import manager

router = APIRouter(prefix="/chats", tags=["chat"])


@router.get("")
async def my_chats(user: OnboardedUser, session: Session) -> list[ChatOut]:
    rows = await chat_service.chats_for(session, user.id)
    return [await presenters.chat_out(session, chat, joined) for chat, joined in rows]


@router.get("/{chat_id}/members")
async def members(chat_id: uuid.UUID, user: OnboardedUser, session: Session) -> list[ChatMemberOut]:
    await chat_service.get_chat_for_member(session, chat_id, user.id)
    rows = await session.execute(
        select(ChatMember, User)
        .join(User, User.id == ChatMember.user_id)
        .where(ChatMember.chat_id == chat_id, ChatMember.left_at.is_(None))
    )
    return [
        ChatMemberOut(user=presenters.public_profile(member_user), is_host=member.is_host)
        for member, member_user in rows
    ]


@router.get("/{chat_id}/messages")
async def messages(
    chat_id: uuid.UUID,
    user: OnboardedUser,
    session: Session,
    before: datetime | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> list[MessageOut]:
    """Oldest first. Pass `before` (the oldest time you have) to page back."""
    await chat_service.get_chat_for_member(session, chat_id, user.id)
    rows = await chat_service.history(session, chat_id, before=before, limit=limit)
    return await presenters.messages_out(session, rows)


@router.post("/{chat_id}/messages", status_code=status.HTTP_201_CREATED)
async def send_message(
    chat_id: uuid.UUID, data: MessageIn, user: OnboardedUser, session: Session
) -> MessageOut:
    chat = await chat_service.get_chat_for_member(session, chat_id, user.id)
    message = await chat_service.post_message(session, chat, user.id, data.body)
    out = (await presenters.messages_out(session, [message]))[0]
    # Save before telling anyone, so nobody sees a message that then fails.
    await session.commit()
    await manager.broadcast(chat_id, {"type": "message", "message": out.model_dump(mode="json")})
    return out


@router.post("/{chat_id}/join")
async def join(chat_id: uuid.UUID, user: OnboardedUser, session: Session) -> ChatOut:
    chat = await session.get(Chat, chat_id)
    if chat is None:
        raise RuleError("Chat not found.", 404)
    await chat_service.join_reunion(session, chat, user.id)
    return await presenters.chat_out(session, chat, joined=True)


@router.post("/{chat_id}/leave")
async def leave(chat_id: uuid.UUID, user: OnboardedUser, session: Session) -> SimpleOk:
    chat = await chat_service.get_chat_for_member(session, chat_id, user.id)
    await chat_service.leave(session, chat, user.id)
    await session.commit()
    await manager.disconnect_user(chat_id, user.id)
    return SimpleOk()


@router.post("/{chat_id}/kick-votes")
async def vote_to_kick(
    chat_id: uuid.UUID, data: KickVoteIn, user: OnboardedUser, session: Session
) -> KickVoteOut:
    """Reunion chats only. Enough votes and they are out, host included."""
    chat = await chat_service.get_chat_for_member(session, chat_id, user.id)
    votes, needed, removed = await chat_service.cast_kick_vote(session, chat, user.id, data.user_id)
    if removed:
        await session.commit()
        await manager.disconnect_user(chat_id, data.user_id)
    return KickVoteOut(votes=votes, votes_needed=needed, removed=removed)


@router.websocket("/{chat_id}/ws")
async def chat_socket(websocket: WebSocket, chat_id: uuid.UUID, token: str | None = None) -> None:
    """Live messages. Send the token as an `Authorization: Bearer ...` header
    (URLSessionWebSocketTask can), or as ?token=... if that is not possible."""
    header = websocket.headers.get("authorization", "")
    if header.lower().startswith("bearer "):
        token = header.split(" ", 1)[1].strip()

    # A WebSocket stays open for a long time, so it can't hold one database
    # session like a normal request does. Each step opens its own.
    async with SessionFactory() as session:
        try:
            if not token:
                raise RuleError("Sign in first.", 401)
            user = await user_from_token(session, token)
            await chat_service.get_chat_for_member(session, chat_id, user.id)
        except (HTTPException, RuleError):
            await websocket.close(code=4401)
            return

    await websocket.accept()
    manager.join(chat_id, user.id, websocket)
    try:
        while True:
            data = await websocket.receive_json()
            body = str(data.get("body", "")) if isinstance(data, dict) else ""
            async with SessionFactory() as session:
                try:
                    chat = await chat_service.get_chat_for_member(session, chat_id, user.id)
                    message = await chat_service.post_message(session, chat, user.id, body)
                    out = (await presenters.messages_out(session, [message]))[0]
                    await session.commit()
                except RuleError as error:
                    await websocket.send_json({"type": "error", "message": error.message})
                    continue
            payload = {"type": "message", "message": out.model_dump(mode="json")}
            await manager.broadcast(chat_id, payload)
    except WebSocketDisconnect:
        pass
    finally:
        manager.leave(chat_id, websocket)
