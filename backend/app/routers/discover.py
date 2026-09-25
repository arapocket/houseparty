"""The Discover list, and liking or passing on someone in it."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Query

from app import presenters
from app.deps import OnboardedUser, Session
from app.schemas import DecisionIn, DecisionOut, DiscoverCardOut, PassedOut
from app.services import matching

router = APIRouter(prefix="/discover", tags=["discover"])


@router.get("")
async def discover(
    user: OnboardedUser,
    session: Session,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[DiscoverCardOut]:
    candidates = await matching.discover(session, user, limit=limit, offset=offset)
    return [
        DiscoverCardOut(
            user=presenters.public_profile(c.user),
            shared_interests=[i.display for i in c.shared_interests],
            distance_km=c.distance_km,
            suggested_for_party_id=c.suggested_for_party_id,
        )
        for c in candidates
    ]


@router.get("/passed")
async def passed(user: OnboardedUser, session: Session) -> list[PassedOut]:
    """People you passed on. Like one from here and it counts like any other like."""
    return [
        PassedOut(
            user=presenters.public_profile(other),
            shared_interests=presenters.shared_interests(user, other),
            passed_at=passed_at,
        )
        for other, passed_at in await matching.list_passed(session, user)
    ]


@router.post("/{user_id}/decision")
async def decide(
    user_id: uuid.UUID, data: DecisionIn, user: OnboardedUser, session: Session
) -> DecisionOut:
    match = await matching.record_decision(session, user, user_id, data.decision)
    return DecisionOut(matched=match is not None, match_id=match.id if match else None)
