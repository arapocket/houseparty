"""Shared FastAPI dependencies.

The `Annotated` aliases at the bottom are what routes actually use:

    async def get_me(user: OnboardedUser, session: Session): ...

FastAPI sees the `Depends(...)` inside the alias and fills the argument in.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models import User
from app.security import decode_access_token

Session = Annotated[AsyncSession, Depends(get_session)]


async def user_from_token(session: AsyncSession, token: str) -> User:
    """Shared by the normal header check and the chat WebSocket."""
    user_id = decode_access_token(token)
    if user_id is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "That session has expired.")

    user = await session.get(User, user_id)
    if user is None or user.deleted_at is not None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Account not found.")
    if user.is_banned:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This account is suspended.")
    return user


async def current_user(
    session: Session,
    authorization: Annotated[str | None, Header()] = None,
) -> User:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sign in first.")
    return await user_from_token(session, authorization.split(" ", 1)[1].strip())


CurrentUser = Annotated[User, Depends(current_user)]


async def onboarded_user(user: CurrentUser) -> User:
    """For everything that needs a finished profile."""
    if not user.is_onboarded:
        raise HTTPException(status.HTTP_428_PRECONDITION_REQUIRED, "Finish your profile first.")
    return user


OnboardedUser = Annotated[User, Depends(onboarded_user)]
