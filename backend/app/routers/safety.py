"""Report and block. Available on profiles, parties and messages."""

from fastapi import APIRouter, status

from app.deps import CurrentUser, Session
from app.schemas import BlockIn, ReportIn, SimpleOk
from app.services import safety

router = APIRouter(tags=["safety"])


@router.post("/reports", status_code=status.HTTP_201_CREATED)
async def report(data: ReportIn, user: CurrentUser, session: Session) -> SimpleOk:
    await safety.report(session, user, data)
    return SimpleOk()


@router.post("/blocks", status_code=status.HTTP_201_CREATED)
async def block(data: BlockIn, user: CurrentUser, session: Session) -> SimpleOk:
    await safety.block(session, user, data.user_id)
    return SimpleOk()
