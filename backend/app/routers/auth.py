"""Sign up and sign in: the same two calls for both."""

from fastapi import APIRouter

from app.deps import Session
from app.schemas import PhoneStartIn, PhoneVerifyIn, SimpleOk, TokenOut
from app.security import create_access_token
from app.services import auth

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/phone/start")
async def start_phone(data: PhoneStartIn, session: Session) -> SimpleOk:
    await auth.start(session, data.phone)
    return SimpleOk()


@router.post("/phone/verify")
async def verify_phone(data: PhoneVerifyIn, session: Session) -> TokenOut:
    user = await auth.verify(session, data.phone, data.code)
    return TokenOut(
        access_token=create_access_token(user.id),
        needs_onboarding=not user.is_onboarded,
    )
