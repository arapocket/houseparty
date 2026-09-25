"""Turning whatever someone types into something we can match on.

The whole app rests on this. If normalisation is too loose, unrelated things
collide ("the office" and "office"); too strict, and nobody ever matches.
"""

from __future__ import annotations

import re
import unicodedata

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import Interest, UserInterest

# Characters we keep because they carry meaning inside an interest name:
# "drum & bass", "d&d", "c++", "hip-hop", "90s", "#1 fan".
_KEEP = "&+#'-"
_PUNCT = re.compile(rf"[^\w\s{re.escape(_KEEP)}]", re.UNICODE)
_SPACES = re.compile(r"\s+")

# Placeholder. Replace with a real list before launch; this only exists so the
# check is wired in from day one.
BLOCKED_WORDS = {"slur1", "slur2"}


def normalize_interest(raw: str) -> str:
    """Collapse spellings of the same thing onto one key.

    >>> normalize_interest("  Radiohead!! ")
    'radiohead'
    >>> normalize_interest("Drum & Bass")
    'drum & bass'
    """
    text = unicodedata.normalize("NFKC", raw)
    text = _PUNCT.sub(" ", text)
    text = _SPACES.sub(" ", text).strip().casefold()
    return text


def clean_display(raw: str) -> str:
    """The spelling we show: the user's own, tidied and length-capped."""
    text = unicodedata.normalize("NFKC", raw)
    text = _SPACES.sub(" ", text).strip()
    return text[: settings.interest_max_length]


def is_acceptable(normalized: str) -> bool:
    if not normalized or len(normalized) < 2:
        return False
    if len(normalized) > settings.interest_max_length:
        return False
    return all(word not in BLOCKED_WORDS for word in normalized.split())


async def get_or_create_interest(session: AsyncSession, raw: str) -> Interest:
    """Find the shared row for this interest, creating it the first time."""
    normalized = normalize_interest(raw)
    existing = await session.scalar(select(Interest).where(Interest.normalized == normalized))
    if existing:
        return existing

    interest = Interest(normalized=normalized, display=clean_display(raw), usage_count=0)
    session.add(interest)
    await session.flush()
    return interest


async def suggest(session: AsyncSession, query: str, limit: int = 8) -> list[Interest]:
    """Suggestions while typing. Popular first, so wording converges over time."""
    normalized = normalize_interest(query)
    if not normalized:
        stmt = (
            select(Interest)
            .where(Interest.is_blocked.is_(False), Interest.usage_count > 0)
            .order_by(Interest.usage_count.desc())
            .limit(limit)
        )
        return list(await session.scalars(stmt))

    # Prefix matches rank above matches in the middle of the string.
    stmt = (
        select(Interest)
        .where(
            Interest.is_blocked.is_(False),
            Interest.normalized.like(f"%{normalized}%"),
        )
        .order_by(
            Interest.normalized.like(f"{normalized}%").desc(),
            Interest.usage_count.desc(),
            Interest.normalized,
        )
        .limit(limit)
    )
    return list(await session.scalars(stmt))


async def recount(session: AsyncSession, interest_id) -> None:
    """Keep usage_count honest after adds and removals."""
    count = await session.scalar(
        select(func.count())
        .select_from(UserInterest)
        .where(UserInterest.interest_id == interest_id)
    )
    interest = await session.get(Interest, interest_id)
    if interest is not None:
        interest.usage_count = count or 0
