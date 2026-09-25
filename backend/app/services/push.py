"""Push notifications.

Services call `queue(...)` while handling a request. Nothing is sent then:
the notifications wait on the database session and go out only after the
request's changes are saved (see `get_session` in db.py). That way nobody
gets "you have a match!" for a like that then failed to save.

Without Apple keys in .env (dev), notifications are written to the server
log instead of sent. With keys, they go to Apple's push service (APNs).
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field

import httpx
import jwt
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings

log = logging.getLogger("houseparty.push")


@dataclass
class Push:
    user_ids: list[uuid.UUID]
    title: str
    body: str
    # Tells the app what to open when the notification is tapped.
    data: dict[str, str] = field(default_factory=dict)


# Every push handed off for delivery, newest last. Tests read this; in
# production it's only ever the last few hundred.
outbox: list[Push] = []


def queue(
    session: AsyncSession, user_ids: list[uuid.UUID], title: str, body: str, **data: str
) -> None:
    if user_ids:
        session.info.setdefault("pushes", []).append(Push(list(user_ids), title, body, data))


async def send_queued(session: AsyncSession) -> None:
    """Call right after a successful commit."""
    pushes: list[Push] = session.info.pop("pushes", [])
    if not pushes:
        return
    outbox.extend(pushes)
    del outbox[:-500]
    # Delivery talks to Apple, which can be slow; don't make the person who
    # triggered it wait.
    asyncio.create_task(_deliver(pushes))


def discard_queued(session: AsyncSession) -> None:
    """The request failed and was rolled back: forget its notifications."""
    session.info.pop("pushes", None)


def apns_configured() -> bool:
    return bool(settings.apns_key_id and settings.apns_team_id and settings.apns_private_key)


async def _deliver(pushes: list[Push]) -> None:
    from app.db import SessionFactory
    from app.models import DeviceToken

    try:
        async with SessionFactory() as session:
            for push in pushes:
                tokens = list(
                    await session.scalars(
                        select(DeviceToken.token).where(DeviceToken.user_id.in_(push.user_ids))
                    )
                )
                if not apns_configured():
                    log.info(
                        "[dev push] to %d device(s): %s — %s", len(tokens), push.title, push.body
                    )
                    continue
                dead = await _send_to_apple(tokens, push)
                if dead:
                    await session.execute(delete(DeviceToken).where(DeviceToken.token.in_(dead)))
            await session.commit()
    except Exception:
        # A failed notification must never take anything else down with it.
        log.exception("push delivery failed")


# --- Apple ---------------------------------------------------------------

_apple_token: tuple[str, float] | None = None


def _apple_auth_token() -> str:
    """Apple wants a short signed token, reused for up to an hour."""
    global _apple_token
    if _apple_token and time.time() - _apple_token[1] < 50 * 60:
        return _apple_token[0]
    token = jwt.encode(
        {"iss": settings.apns_team_id, "iat": int(time.time())},
        settings.apns_private_key.replace("\\n", "\n"),
        algorithm="ES256",
        headers={"kid": settings.apns_key_id},
    )
    _apple_token = (token, time.time())
    return token


async def _send_to_apple(tokens: list[str], push: Push) -> list[str]:
    """Returns tokens Apple says are dead (app deleted), so we can forget them."""
    host = (
        "https://api.sandbox.push.apple.com"
        if settings.apns_use_sandbox
        else "https://api.push.apple.com"
    )
    # The "open"/"id" extras tell the app which screen to show when tapped.
    payload: dict[str, object] = {
        "aps": {"alert": {"title": push.title, "body": push.body}, "sound": "default"},
        **push.data,
    }
    headers = {
        "authorization": f"bearer {_apple_auth_token()}",
        "apns-topic": settings.apns_bundle_id,
        "apns-push-type": "alert",
    }
    dead: list[str] = []
    # Apple only speaks HTTP/2.
    async with httpx.AsyncClient(http2=True, timeout=10) as client:
        for token in tokens:
            response = await client.post(f"{host}/3/device/{token}", json=payload, headers=headers)
            if response.status_code == 410:
                dead.append(token)
            elif response.status_code != 200:
                log.warning("APNs said %s: %s", response.status_code, response.text)
    return dead
