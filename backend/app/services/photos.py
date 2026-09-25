"""Profile photos.

What happens to an upload, in order:

  1. Check it really is a JPEG or PNG (by opening it, not by trusting the
     file name) and not absurdly large.
  2. Re-save it as a fresh JPEG, at most 1600px on the long side. This throws
     away the hidden data phones attach to photos, including the GPS spot
     where it was taken, which would otherwise leak exactly where someone
     lives.
  3. Run the automatic check for nudity, violence and the like.
  4. Store it. If the check passed, it's the profile photo straight away.
     If not, it waits in the admin page and the old photo stays up.

Storage and the check both have a "dev" mode that needs no accounts: files
go in backend/uploads/ and every photo passes.
"""

from __future__ import annotations

import asyncio
import io
import logging
import uuid
from pathlib import Path

from PIL import Image, UnidentifiedImageError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.errors import RuleError
from app.models import User

log = logging.getLogger("houseparty.photos")

MAX_UPLOAD_BYTES = 10 * 1024 * 1024
MAX_SIDE = 1600
UPLOAD_DIR = Path(__file__).resolve().parents[2] / "uploads"

# Moderation labels that hold a photo back. Covers the names Amazon has used
# in both the older and newer versions of its label list. Deliberately not
# on the list: alcohol, smoking, swimwear. It's a party app.
BLOCKING_LABELS = {
    "Explicit Nudity",
    "Explicit",
    "Non-Explicit Nudity of Intimate parts and Kissing",
    "Violence",
    "Graphic Violence",
    "Visually Disturbing",
    "Hate Symbols",
}


def clean_image(raw: bytes) -> bytes:
    """Steps 1 and 2: validate, shrink, and strip hidden data."""
    if len(raw) > MAX_UPLOAD_BYTES:
        raise RuleError("That photo is too big. Try one under 10 MB.", 413)
    try:
        with Image.open(io.BytesIO(raw)) as image:
            if image.format not in ("JPEG", "PNG"):
                raise RuleError("Photos need to be JPEG or PNG.", 415)
            rgb = image.convert("RGB")  # also drops transparency and metadata
            rgb.thumbnail((MAX_SIDE, MAX_SIDE))
            out = io.BytesIO()
            # No exif= argument, so none of the original's metadata is copied.
            rgb.save(out, format="JPEG", quality=85, optimize=True)
            return out.getvalue()
    except (UnidentifiedImageError, OSError) as error:
        raise RuleError("That file isn't a photo we can read.", 415) from error


def moderation_labels(jpeg: bytes) -> set[str]:
    """Step 3. Returns the names of anything that should hold the photo back.

    Blocking network call, so callers run it in a thread.
    """
    if settings.moderation_backend == "off":
        return set()

    import boto3  # only needed when moderation is switched on

    client = boto3.client("rekognition", region_name=settings.aws_region)
    result = client.detect_moderation_labels(Image={"Bytes": jpeg}, MinConfidence=80)
    found: set[str] = set()
    for label in result.get("ModerationLabels", []):
        for name in (label.get("Name"), label.get("ParentName")):
            if name in BLOCKING_LABELS:
                found.add(name)
    return found


def store(jpeg: bytes) -> str:
    """Step 4. Saves the file and returns the path the app loads it from.

    Paths, not full URLs: the app puts its own server address in front, so
    the same database works whatever the server's address is.
    """
    name = f"{uuid.uuid4().hex}.jpg"

    if settings.storage_backend == "local":
        UPLOAD_DIR.mkdir(exist_ok=True)
        (UPLOAD_DIR / name).write_bytes(jpeg)
        return f"/uploads/{name}"

    import boto3

    # On AWS, boto3 finds the server's permissions by itself; no keys here.
    boto3.client("s3", region_name=settings.aws_region).put_object(
        Bucket=settings.s3_bucket,
        Key=f"photos/{name}",
        Body=jpeg,
        ContentType="image/jpeg",
        CacheControl="public, max-age=31536000, immutable",  # names never get reused
    )
    return f"/photos/{name}"


async def upload_profile_photo(session: AsyncSession, user: User, raw: bytes) -> bool:
    """Returns True if the photo went live, False if it's waiting for review."""
    jpeg = clean_image(raw)
    # boto3 and file writes block, so they run off the main thread to keep the
    # server answering other people meanwhile.
    flagged = await asyncio.to_thread(moderation_labels, jpeg)
    url = await asyncio.to_thread(store, jpeg)

    if flagged:
        log.info("photo for %s held for review: %s", user.id, ", ".join(sorted(flagged)))
        user.pending_photo_url = url
        user.pending_photo_reason = ", ".join(sorted(flagged))
        await session.flush()
        return False

    user.photo_url = url
    user.pending_photo_url = None
    user.pending_photo_reason = None
    await session.flush()
    return True


def approve_pending(user: User) -> None:
    """Admin said the held photo is fine."""
    if user.pending_photo_url:
        user.photo_url = user.pending_photo_url
    user.pending_photo_url = None
    user.pending_photo_reason = None


def reject_pending(user: User) -> None:
    """Admin said no. The file stays in storage for the record; it's just
    never shown."""
    user.pending_photo_url = None
    user.pending_photo_reason = None
