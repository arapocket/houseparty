"""Profile photo uploads: cleaning, the automatic check, and review."""

import io

import httpx
import pytest
from PIL import Image

from app.services import photos
from tests.conftest import sign_up


def make_jpeg(with_gps: bool = False, size=(2400, 1800)) -> bytes:
    image = Image.new("RGB", size, (255, 80, 140))
    exif = Image.Exif()
    if with_gps:
        # GPS block with a latitude, the way a phone camera writes it.
        exif[0x8825] = {1: "N", 2: (40.0, 43.0, 15.0), 3: "W", 4: (74.0, 0.0, 2.0)}
    out = io.BytesIO()
    image.save(out, format="JPEG", exif=exif)
    return out.getvalue()


@pytest.fixture(autouse=True)
def uploads_in_tmp(tmp_path, monkeypatch):
    monkeypatch.setattr(photos, "UPLOAD_DIR", tmp_path)
    return tmp_path


def test_cleaning_strips_location_and_shrinks() -> None:
    original = make_jpeg(with_gps=True)
    assert Image.open(io.BytesIO(original)).getexif().get_ifd(0x8825)  # it's really there

    cleaned = Image.open(io.BytesIO(photos.clean_image(original)))
    assert not cleaned.getexif()
    assert max(cleaned.size) == photos.MAX_SIDE


def test_non_images_are_refused() -> None:
    with pytest.raises(photos.RuleError):
        photos.clean_image(b"definitely not a photo")


async def test_upload_goes_live(client: httpx.AsyncClient, uploads_in_tmp) -> None:
    ana = await sign_up(client, "Ana", ["Radiohead"])
    r = await client.post(
        "/me/photo", headers=ana.headers, files={"photo": ("me.jpg", make_jpeg(), "image/jpeg")}
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["live"] is True
    assert body["me"]["photo_url"].startswith("/uploads/")
    assert body["me"]["photo_in_review"] is False
    assert len(list(uploads_in_tmp.iterdir())) == 1


async def test_flagged_upload_waits_for_review(client: httpx.AsyncClient, monkeypatch) -> None:
    ana = await sign_up(client, "Ana", ["Radiohead"])
    await client.post(
        "/me/photo", headers=ana.headers, files={"photo": ("a.jpg", make_jpeg(), "image/jpeg")}
    )
    first_url = (await client.get("/me", headers=ana.headers)).json()["photo_url"]

    monkeypatch.setattr(photos, "moderation_labels", lambda jpeg: {"Explicit Nudity"})
    r = await client.post(
        "/me/photo", headers=ana.headers, files={"photo": ("b.jpg", make_jpeg(), "image/jpeg")}
    )
    body = r.json()
    assert body["live"] is False
    # The old photo stays up; the new one is out of sight.
    assert body["me"]["photo_url"] == first_url
    assert body["me"]["photo_in_review"] is True


def test_admin_decisions() -> None:
    from app.models import User

    user = User(photo_url="old", pending_photo_url="new", pending_photo_reason="Violence")
    photos.reject_pending(user)
    assert (user.photo_url, user.pending_photo_url) == ("old", None)

    user.pending_photo_url = "new"
    photos.approve_pending(user)
    assert (user.photo_url, user.pending_photo_url) == ("new", None)


async def test_profile_url_cannot_be_set_directly(client: httpx.AsyncClient) -> None:
    ana = await sign_up(client, "Ana", ["Radiohead"])
    await client.patch("/me", headers=ana.headers, json={"photo_url": "https://evil.example/x.jpg"})
    assert (await client.get("/me", headers=ana.headers)).json()["photo_url"] is None
