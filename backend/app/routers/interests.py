"""Suggestions while someone types an interest."""

from typing import Annotated

from fastapi import APIRouter, Query

from app.deps import CurrentUser, Session
from app.schemas import InterestSuggestionOut
from app.services import interests

router = APIRouter(prefix="/interests", tags=["interests"])


@router.get("/suggest")
async def suggest_interests(
    session: Session,
    _user: CurrentUser,
    q: Annotated[str, Query(max_length=40)] = "",
) -> list[InterestSuggestionOut]:
    rows = await interests.suggest(session, q)
    return [InterestSuggestionOut(display=i.display, usage_count=i.usage_count) for i in rows]
