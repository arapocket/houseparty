"""Your own profile, and looking at someone else's."""

import uuid

from fastapi import APIRouter, UploadFile, status
from sqlalchemy import delete, select

from app import presenters
from app.deps import CurrentUser, OnboardedUser, Session
from app.models import DeviceToken
from app.schemas import (
    DeviceIn,
    InterestsIn,
    MeOut,
    PhotoOut,
    ProfileIn,
    PublicProfileOut,
    SimpleOk,
)
from app.services import photos, profiles

router = APIRouter(tags=["profile"])


@router.get("/me")
async def get_me(user: CurrentUser) -> MeOut:
    return presenters.me(user)


# CurrentUser, not OnboardedUser: this is how onboarding gets finished.
@router.patch("/me")
async def update_me(data: ProfileIn, user: CurrentUser, session: Session) -> MeOut:
    await profiles.update_profile(session, user, data)
    return presenters.me(user)


@router.put("/me/interests")
async def set_my_interests(data: InterestsIn, user: CurrentUser, session: Session) -> MeOut:
    await profiles.set_interests(session, user, data.interests)
    return presenters.me(user)


@router.post("/me/photo")
async def upload_photo(photo: UploadFile, user: CurrentUser, session: Session) -> PhotoOut:
    """Send the photo as a multipart form field called "photo". It's live
    right away unless the automatic check flags it for a person to review."""
    raw = await photo.read(photos.MAX_UPLOAD_BYTES + 1)
    live = await photos.upload_profile_photo(session, user, raw)
    return PhotoOut(live=live, me=presenters.me(user))


@router.delete("/me/photo")
async def remove_photo(user: CurrentUser, session: Session) -> MeOut:
    user.photo_url = None
    user.pending_photo_url = None
    user.pending_photo_reason = None
    await session.flush()
    return presenters.me(user)


@router.post("/me/devices")
async def register_device(data: DeviceIn, user: CurrentUser, session: Session) -> SimpleOk:
    """Called by the app when iOS gives it a push token. If the same phone
    was signed in as someone else before, it now belongs to this account."""
    existing = await session.scalar(select(DeviceToken).where(DeviceToken.token == data.token))
    if existing:
        existing.user_id = user.id
    else:
        session.add(DeviceToken(user_id=user.id, token=data.token))
    return SimpleOk()


@router.delete("/me/devices/{token}")
async def forget_device(token: str, user: CurrentUser, session: Session) -> SimpleOk:
    """Called on sign-out, so a shared phone stops getting your notifications."""
    await session.execute(
        delete(DeviceToken).where(DeviceToken.token == token, DeviceToken.user_id == user.id)
    )
    return SimpleOk()


@router.delete("/me", status_code=status.HTTP_204_NO_CONTENT)
async def delete_me(user: CurrentUser, session: Session) -> None:
    await profiles.delete_account(session, user)


@router.get("/users/{user_id}")
async def get_user(user_id: uuid.UUID, user: OnboardedUser, session: Session) -> PublicProfileOut:
    other = await profiles.get_visible_user(session, user, user_id)
    return presenters.public_profile(other)
