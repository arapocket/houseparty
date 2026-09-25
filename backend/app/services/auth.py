"""Signing in with a phone number.

  1. POST /auth/phone/start   we text a 6-digit code
  2. POST /auth/phone/verify  they send it back, we hand out a token

The same two steps both sign up new people and sign in returning ones.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import sms
from app.config import settings
from app.errors import RuleError
from app.models import PhoneVerification, User
from app.security import codes_match, generate_code, hash_code


def utcnow() -> datetime:
    return datetime.now(UTC)


async def start(session: AsyncSession, phone: str) -> None:
    an_hour_ago = utcnow() - timedelta(hours=1)
    recent = await session.scalar(
        select(func.count())
        .select_from(PhoneVerification)
        .where(PhoneVerification.phone == phone, PhoneVerification.created_at > an_hour_ago)
    )
    if (recent or 0) >= settings.verification_starts_per_hour:
        raise RuleError("Too many codes for this number. Try again in an hour.", 429)

    # We keep a row even when Twilio does the sending, because the row is also
    # what the hourly limit above counts.
    code = generate_code()
    session.add(
        PhoneVerification(
            phone=phone,
            code_hash=hash_code(code),
            expires_at=utcnow() + timedelta(seconds=settings.verification_code_ttl_seconds),
        )
    )
    await session.flush()
    await sms.send_code(phone, code)


async def verify(session: AsyncSession, phone: str, code: str) -> User:
    """Check the code, then find or create the account for this number."""
    if sms.twilio_configured():
        if not await sms.check_code(phone, code):
            raise RuleError("That code is wrong or has expired.", 401)
    else:
        await _check_stored_code(session, phone, code)

    user = await session.scalar(select(User).where(User.phone == phone))
    if user is None:
        user = User(
            phone=phone,
            search_radius_km=settings.default_radius_km,
            invite_cap=settings.default_invite_cap,
            interests=[],
        )
        session.add(user)
    if user.is_banned:
        raise RuleError("This account is suspended.", 403)
    user.phone_verified_at = utcnow()
    await session.flush()
    return user


async def _check_stored_code(session: AsyncSession, phone: str, code: str) -> None:
    row = await session.scalar(
        select(PhoneVerification)
        .where(
            PhoneVerification.phone == phone,
            PhoneVerification.consumed_at.is_(None),
            PhoneVerification.expires_at > utcnow(),
        )
        .order_by(PhoneVerification.created_at.desc())
        .limit(1)
    )
    if row is None:
        raise RuleError("That code has expired. Ask for a new one.", 401)
    if row.attempts >= settings.verification_max_attempts:
        raise RuleError("Too many wrong tries. Ask for a new code.", 429)

    row.attempts += 1
    if not codes_match(code, row.code_hash):
        # Commit before raising. Raising rolls the request back, which would
        # also undo the attempt count and let someone guess forever.
        await session.commit()
        raise RuleError("That code is wrong.", 401)

    row.consumed_at = utcnow()
