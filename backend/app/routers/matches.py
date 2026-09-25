"""Everyone you have matched with. These are the people you can invite."""

from fastapi import APIRouter

from app import presenters
from app.deps import OnboardedUser, Session
from app.schemas import MatchOut
from app.services import matching

router = APIRouter(prefix="/matches", tags=["matches"])


@router.get("")
async def list_matches(user: OnboardedUser, session: Session) -> list[MatchOut]:
    out = []
    for other, matched_at in await matching.list_matches(session, user):
        out.append(
            MatchOut(
                user=presenters.public_profile(other),
                matched_at=matched_at,
                shared_interests=presenters.shared_interests(user, other),
            )
        )
    return out
