"""Who gets notified about what. Nothing is really sent in tests; every
notification that would go out lands in push.outbox."""

from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy import update

from app.db import SessionFactory
from app.models import Party
from app.services import push
from app.services.parties import send_reminders
from tests.conftest import match, sign_up
from tests.test_api import party_json


@pytest.fixture(autouse=True)
def empty_outbox():
    push.outbox.clear()


def sent_to(person) -> list[push.Push]:
    return [p for p in push.outbox if any(str(u) == person.id for u in p.user_ids)]


async def test_match_notifies_both(client: httpx.AsyncClient) -> None:
    ana = await sign_up(client, "Ana", ["Radiohead"])
    ben = await sign_up(client, "Ben", ["Radiohead"])
    await client.post(
        f"/discover/{ben.id}/decision", headers=ana.headers, json={"decision": "like"}
    )
    assert push.outbox == []  # a one-sided like tells nobody
    await client.post(
        f"/discover/{ana.id}/decision", headers=ben.headers, json={"decision": "like"}
    )
    assert [p.body for p in sent_to(ana)] == ["You and Ben liked each other."]
    assert [p.body for p in sent_to(ben)] == ["You and Ana liked each other."]


async def test_invite_and_accept(client: httpx.AsyncClient) -> None:
    host = await sign_up(client, "Host", ["Radiohead"])
    guest = await sign_up(client, "Guest", ["Radiohead"])
    await match(client, host, guest)
    push.outbox.clear()

    party = (await client.post("/parties", headers=host.headers, json=party_json())).json()
    invite = (
        await client.post(
            f"/parties/{party['id']}/invites", headers=host.headers, json={"user_id": guest.id}
        )
    ).json()
    assert sent_to(guest)[0].title == "Host invited you to a party"
    assert sent_to(guest)[0].data == {"open": "party", "id": party["id"]}

    await client.post(
        f"/invites/{invite['id']}/respond", headers=guest.headers, json={"accept": True}
    )
    assert sent_to(host)[-1].title == "Guest is coming"


async def test_failed_request_sends_nothing(client: httpx.AsyncClient) -> None:
    host = await sign_up(client, "Host", ["Radiohead"])
    stranger = await sign_up(client, "Stranger", ["Radiohead"])
    party = (await client.post("/parties", headers=host.headers, json=party_json())).json()
    r = await client.post(
        f"/parties/{party['id']}/invites", headers=host.headers, json={"user_id": stranger.id}
    )
    assert r.status_code == 403
    assert sent_to(stranger) == []


async def test_messages_skip_sender_muted_and_blocked(client: httpx.AsyncClient) -> None:
    host = await sign_up(client, "Host", ["Radiohead"])
    guests = [await sign_up(client, n, ["Radiohead"]) for n in ("A", "B", "C")]
    party = (await client.post("/parties", headers=host.headers, json=party_json())).json()
    for guest in guests:
        await match(client, host, guest)
        invite = (
            await client.post(
                f"/parties/{party['id']}/invites", headers=host.headers, json={"user_id": guest.id}
            )
        ).json()
        await client.post(
            f"/invites/{invite['id']}/respond", headers=guest.headers, json={"accept": True}
        )
    chat_id = (await client.get("/chats", headers=host.headers)).json()[0]["id"]
    a, b, c = guests

    r = await client.post(f"/chats/{chat_id}/mute", headers=b.headers, json={"muted": True})
    assert r.json()["muted"] is True
    await client.post("/blocks", headers=c.headers, json={"user_id": a.id})
    push.outbox.clear()

    await client.post(
        f"/chats/{chat_id}/messages", headers=a.headers, json={"body": "Bringing snacks"}
    )
    notified = {str(u) for p in push.outbox for u in p.user_ids}
    assert notified == {host.id}  # not A (sender), not B (muted), not C (blocked A)
    assert push.outbox[0].body == "A: Bringing snacks"


async def test_reminder_goes_out_once(client: httpx.AsyncClient) -> None:
    host = await sign_up(client, "Host", ["Radiohead"])
    party = (await client.post("/parties", headers=host.headers, json=party_json())).json()
    async with SessionFactory() as session:
        in_an_hour = datetime.now(UTC) + timedelta(hours=1)
        await session.execute(
            update(Party).where(Party.id == party["id"]).values(starts_at=in_an_hour)
        )
        await session.commit()

    for _ in range(2):  # the job runs every few minutes; only the first run reminds
        async with SessionFactory() as session:
            await send_reminders(session)
            await session.commit()
            await push.send_queued(session)
    assert [p.title for p in sent_to(host)] == ["Starting soon"]


async def test_devices_register_and_forget(client: httpx.AsyncClient) -> None:
    ana = await sign_up(client, "Ana", ["Radiohead"])
    r = await client.post("/me/devices", headers=ana.headers, json={"token": "abc123def456"})
    assert r.status_code == 200
    r = await client.delete("/me/devices/abc123def456", headers=ana.headers)
    assert r.status_code == 200
