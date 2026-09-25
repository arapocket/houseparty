"""End-to-end through the API, against a real database.

Each test reads as a small story about one product rule.
"""

from datetime import UTC, date, datetime, timedelta

import httpx
from sqlalchemy import select, update

from app.db import SessionFactory
from app.models import Party, PhoneVerification, User
from app.services.parties import complete_finished_parties
from tests.conftest import TEST_CODE, match, sign_up

# About 1 km, 5 km and 80 km north of the default test location.
NEAR = {"lat": 40.7218, "lon": -74.0060}
MID = {"lat": 40.7578, "lon": -74.0060}
FAR = {"lat": 41.4328, "lon": -74.0060}


def party_json(**overrides) -> dict:
    body = {
        "title": "Kid A listening party",
        "description": "Front to back, lights off.",
        "starts_at": (datetime.now(UTC) + timedelta(days=3)).isoformat(),
        "neighborhood": "Tribeca",
        "latitude": 40.7163,
        "longitude": -74.0086,
        "address": "12 Secret St, Apt 4",
        "interests": ["Radiohead"],
    }
    body.update(overrides)
    return body


# --- sign up -----------------------------------------------------------------


async def test_new_user_must_finish_profile(client: httpx.AsyncClient) -> None:
    phone = "+14155550199"
    await client.post("/auth/phone/start", json={"phone": phone})
    r = await client.post("/auth/phone/verify", json={"phone": phone, "code": TEST_CODE})
    assert r.json()["needs_onboarding"] is True
    headers = {"Authorization": f"Bearer {r.json()['access_token']}"}

    r = await client.get("/discover", headers=headers)
    assert r.status_code == 428


async def test_under_21_is_turned_away(client: httpx.AsyncClient) -> None:
    phone = "+14155550198"
    await client.post("/auth/phone/start", json={"phone": phone})
    r = await client.post("/auth/phone/verify", json={"phone": phone, "code": TEST_CODE})
    headers = {"Authorization": f"Bearer {r.json()['access_token']}"}

    almost_21 = date.today().replace(year=date.today().year - 21) + timedelta(days=1)
    r = await client.patch(
        "/me", headers=headers, json={"first_name": "Kid", "birthdate": almost_21.isoformat()}
    )
    assert r.status_code == 403


async def test_birthdate_cannot_be_changed(client: httpx.AsyncClient) -> None:
    ana = await sign_up(client, "Ana", ["Radiohead"])
    r = await client.patch("/me", headers=ana.headers, json={"birthdate": "1990-01-01"})
    assert r.status_code == 400


async def test_wrong_codes_are_counted_and_limited(client: httpx.AsyncClient) -> None:
    phone = "+14155550197"
    await client.post("/auth/phone/start", json={"phone": phone})
    for _ in range(5):
        r = await client.post("/auth/phone/verify", json={"phone": phone, "code": "000000"})
        assert r.status_code == 401
    # Even the right code is refused once the tries are used up.
    r = await client.post("/auth/phone/verify", json={"phone": phone, "code": TEST_CODE})
    assert r.status_code == 429


async def test_code_requests_are_rate_limited(client: httpx.AsyncClient) -> None:
    for _ in range(5):
        r = await client.post("/auth/phone/start", json={"phone": "+14155550196"})
        assert r.status_code == 200
    r = await client.post("/auth/phone/start", json={"phone": "+14155550196"})
    assert r.status_code == 429


async def test_codes_are_stored_hashed(client: httpx.AsyncClient) -> None:
    await client.post("/auth/phone/start", json={"phone": "+14155550195"})
    async with SessionFactory() as session:
        row = await session.scalar(select(PhoneVerification))
        assert row is not None and TEST_CODE not in row.code_hash


# --- interests ---------------------------------------------------------------


async def test_interests_dedupe_and_suggest_by_popularity(client: httpx.AsyncClient) -> None:
    ana = await sign_up(client, "Ana", ["Radiohead", "radiohead!!", "Board games"])
    r = await client.get("/me", headers=ana.headers)
    assert r.json()["interests"] == ["Radiohead", "Board games"]

    await sign_up(client, "Ben", ["RADIOHEAD"])
    await sign_up(client, "Cal", ["Radio plays"])

    r = await client.get("/interests/suggest", params={"q": "radi"}, headers=ana.headers)
    suggestions = r.json()
    # First spelling wins, and the more popular one comes first.
    assert suggestions[0] == {"display": "Radiohead", "usage_count": 2}
    assert suggestions[1]["display"] == "Radio plays"


async def test_too_many_interests_rejected(client: httpx.AsyncClient) -> None:
    ana = await sign_up(client, "Ana", ["Radiohead"])
    r = await client.put(
        "/me/interests", headers=ana.headers, json={"interests": [f"thing {i}" for i in range(13)]}
    )
    assert r.status_code == 422


# --- discover ----------------------------------------------------------------


async def test_discover_ranks_by_shared_interests_then_distance(
    client: httpx.AsyncClient,
) -> None:
    me = await sign_up(client, "Me", ["Radiohead", "Board games", "Natural wine"])
    await sign_up(client, "OneShared", ["Radiohead"], **NEAR)
    await sign_up(client, "TwoSharedFar", ["Radiohead", "Board games"], **MID)
    await sign_up(client, "TwoSharedNear", ["Radiohead", "Natural wine"], **NEAR)
    await sign_up(client, "NothingShared", ["Golf"], **NEAR)
    await sign_up(client, "TooFar", ["Radiohead", "Board games", "Natural wine"], **FAR)

    r = await client.get("/discover", headers=me.headers)
    names = [card["user"]["first_name"] for card in r.json()]
    assert names == ["TwoSharedNear", "TwoSharedFar", "OneShared"]

    first = r.json()[0]
    assert sorted(first["shared_interests"]) == ["Natural wine", "Radiohead"]
    assert first["distance_km"] == 1
    # Exact location never leaves the server.
    assert "latitude" not in first["user"] and "phone" not in first["user"]


async def test_passed_people_leave_discover(client: httpx.AsyncClient) -> None:
    me = await sign_up(client, "Me", ["Radiohead"])
    ben = await sign_up(client, "Ben", ["Radiohead"])
    await client.post(f"/discover/{ben.id}/decision", headers=me.headers, json={"decision": "pass"})
    r = await client.get("/discover", headers=me.headers)
    assert r.json() == []


async def test_block_hides_both_ways(client: httpx.AsyncClient) -> None:
    me = await sign_up(client, "Me", ["Radiohead"])
    ben = await sign_up(client, "Ben", ["Radiohead"])
    r = await client.post("/blocks", headers=me.headers, json={"user_id": ben.id})
    assert r.status_code == 201
    assert (await client.get("/discover", headers=me.headers)).json() == []
    assert (await client.get("/discover", headers=ben.headers)).json() == []
    r = await client.post(
        f"/discover/{me.id}/decision", headers=ben.headers, json={"decision": "like"}
    )
    assert r.status_code == 404


# --- matching and parties ----------------------------------------------------


async def test_mutual_like_makes_a_match(client: httpx.AsyncClient) -> None:
    ana = await sign_up(client, "Ana", ["Radiohead"])
    ben = await sign_up(client, "Ben", ["Radiohead"])

    r = await client.post(
        f"/discover/{ben.id}/decision", headers=ana.headers, json={"decision": "like"}
    )
    assert r.json()["matched"] is False
    r = await client.post(
        f"/discover/{ana.id}/decision", headers=ben.headers, json={"decision": "like"}
    )
    assert r.json()["matched"] is True

    r = await client.get("/matches", headers=ana.headers)
    assert [m["user"]["first_name"] for m in r.json()] == ["Ben"]
    assert r.json()[0]["shared_interests"] == ["Radiohead"]


async def test_host_can_only_invite_matches(client: httpx.AsyncClient) -> None:
    host = await sign_up(client, "Host", ["Radiohead"])
    stranger = await sign_up(client, "Stranger", ["Radiohead"])
    party = (await client.post("/parties", headers=host.headers, json=party_json())).json()

    r = await client.post(
        f"/parties/{party['id']}/invites", headers=host.headers, json={"user_id": stranger.id}
    )
    assert r.status_code == 403


async def test_party_is_invisible_to_uninvited(client: httpx.AsyncClient) -> None:
    host = await sign_up(client, "Host", ["Radiohead"])
    nosy = await sign_up(client, "Nosy", ["Radiohead"])
    party = (await client.post("/parties", headers=host.headers, json=party_json())).json()

    r = await client.get(f"/parties/{party['id']}", headers=nosy.headers)
    assert r.status_code == 404


async def test_address_hidden_until_accepted(client: httpx.AsyncClient) -> None:
    host = await sign_up(client, "Host", ["Radiohead"])
    guest = await sign_up(client, "Guest", ["Radiohead"], **MID)
    await match(client, host, guest)
    party = (await client.post("/parties", headers=host.headers, json=party_json())).json()
    assert party["address"] == "12 Secret St, Apt 4"  # the host sees it

    r = await client.post(
        f"/parties/{party['id']}/invites", headers=host.headers, json={"user_id": guest.id}
    )
    invite_id = r.json()["id"]

    before = (await client.get("/invites", headers=guest.headers)).json()[0]["party"]
    assert before["address"] is None
    assert before["neighborhood"] == "Tribeca"
    assert before["distance_km"] == 5
    assert before["host"]["first_name"] == "Host"

    r = await client.post(
        f"/invites/{invite_id}/respond", headers=guest.headers, json={"accept": True}
    )
    assert r.json()["party"]["address"] == "12 Secret St, Apt 4"


async def test_invite_cap(client: httpx.AsyncClient) -> None:
    host = await sign_up(client, "Host", ["Radiohead"])
    guests = [await sign_up(client, f"G{i}", ["Radiohead"]) for i in range(3)]
    for guest in guests:
        await match(client, host, guest)

    # Pretend the cap is 2 rather than making 21 people.
    async with SessionFactory() as session:
        await session.execute(update(User).values(invite_cap=2))
        await session.commit()
    party = (await client.post("/parties", headers=host.headers, json=party_json())).json()

    for guest in guests[:2]:
        r = await client.post(
            f"/parties/{party['id']}/invites", headers=host.headers, json={"user_id": guest.id}
        )
        assert r.status_code == 201
    r = await client.post(
        f"/parties/{party['id']}/invites", headers=host.headers, json={"user_id": guests[2].id}
    )
    assert r.status_code == 409

    r = await client.post(
        f"/parties/{party['id']}/bigger", headers=host.headers, json={"requested_cap": 40}
    )
    assert r.status_code == 201


async def test_host_removes_guest_from_party_and_chat(client: httpx.AsyncClient) -> None:
    host = await sign_up(client, "Host", ["Radiohead"])
    guest = await sign_up(client, "Guest", ["Radiohead"])
    await match(client, host, guest)
    party = (await client.post("/parties", headers=host.headers, json=party_json())).json()
    invite_id = (
        await client.post(
            f"/parties/{party['id']}/invites", headers=host.headers, json={"user_id": guest.id}
        )
    ).json()["id"]
    await client.post(f"/invites/{invite_id}/respond", headers=guest.headers, json={"accept": True})

    chats = (await client.get("/chats", headers=guest.headers)).json()
    assert [c["kind"] for c in chats] == ["planning"]

    r = await client.delete(f"/parties/{party['id']}/invites/{invite_id}", headers=host.headers)
    assert r.status_code == 200
    assert (await client.get("/chats", headers=guest.headers)).json() == []
    assert (await client.get(f"/parties/{party['id']}", headers=guest.headers)).status_code == 404


async def test_cancelling_keeps_chat_open(client: httpx.AsyncClient) -> None:
    host = await sign_up(client, "Host", ["Radiohead"])
    party = (await client.post("/parties", headers=host.headers, json=party_json())).json()
    await client.post(f"/parties/{party['id']}/cancel", headers=host.headers)

    chat = (await client.get("/chats", headers=host.headers)).json()[0]
    r = await client.post(
        f"/chats/{chat['id']}/messages",
        headers=host.headers,
        json={"body": "Sorry all, rain check"},
    )
    assert r.status_code == 201
    chat = (await client.get("/chats", headers=host.headers)).json()[0]
    assert chat["last_message"] == "Sorry all, rain check"
    assert chat["last_sender_name"] == "Host"


async def test_introductions_surface_both_people(client: httpx.AsyncClient) -> None:
    host = await sign_up(client, "Host", ["Radiohead"])
    guest = await sign_up(client, "Guest", ["Radiohead"])
    friend = await sign_up(client, "Friend", ["Golf"])  # shares nothing with the host
    bystander = await sign_up(client, "Bystander", ["Golf"])
    await match(client, host, guest)
    party = (await client.post("/parties", headers=host.headers, json=party_json())).json()
    invite_id = (
        await client.post(
            f"/parties/{party['id']}/invites", headers=host.headers, json={"user_id": guest.id}
        )
    ).json()["id"]
    await client.post(f"/invites/{invite_id}/respond", headers=guest.headers, json={"accept": True})

    r = await client.post(
        f"/parties/{party['id']}/suggestions", headers=guest.headers, json={"user_id": friend.id}
    )
    assert r.status_code == 201

    host_sees = (await client.get("/discover", headers=host.headers)).json()
    assert host_sees[0]["user"]["first_name"] == "Friend"
    assert host_sees[0]["suggested_for_party_id"] == party["id"]

    friend_sees = (await client.get("/discover", headers=friend.headers)).json()
    assert friend_sees[0]["user"]["first_name"] == "Host"

    # Someone unrelated gets no boost and no badge.
    bystander_sees = (await client.get("/discover", headers=bystander.headers)).json()
    assert all(card["suggested_for_party_id"] is None for card in bystander_sees)

    # Once they match, the host can invite.
    await match(client, host, friend)
    r = await client.post(
        f"/parties/{party['id']}/invites", headers=host.headers, json={"user_id": friend.id}
    )
    assert r.status_code == 201


# --- after the party ---------------------------------------------------------


async def _throw_finished_party(client: httpx.AsyncClient, host, guests) -> str:
    """A party with these guests that has already happened. Returns its id."""
    for guest in guests:
        await match(client, host, guest)
    party = (await client.post("/parties", headers=host.headers, json=party_json())).json()
    for guest in guests:
        invite_id = (
            await client.post(
                f"/parties/{party['id']}/invites", headers=host.headers, json={"user_id": guest.id}
            )
        ).json()["id"]
        await client.post(
            f"/invites/{invite_id}/respond", headers=guest.headers, json={"accept": True}
        )

    async with SessionFactory() as session:
        yesterday = datetime.now(UTC) - timedelta(days=1)
        await session.execute(
            update(Party).where(Party.id == party["id"]).values(starts_at=yesterday)
        )
        finished = await complete_finished_parties(session)
        await session.commit()
    assert len(finished) == 1
    return party["id"]


async def test_reunion_chat_is_opt_in_and_votes_can_remove_host(
    client: httpx.AsyncClient,
) -> None:
    host = await sign_up(client, "Host", ["Radiohead"])
    guests = [await sign_up(client, n, ["Radiohead"]) for n in ("A", "B", "C")]
    await _throw_finished_party(client, host, guests)

    everyone = [host, *guests]
    reunion = next(
        c
        for c in (await client.get("/chats", headers=host.headers)).json()
        if c["kind"] == "reunion"
    )
    assert reunion["joined"] is False and reunion["can_join"] is True
    for person in everyone:
        r = await client.post(f"/chats/{reunion['id']}/join", headers=person.headers)
        assert r.status_code == 200

    # 3 others, so 2 votes are needed to remove the host.
    url = f"/chats/{reunion['id']}/kick-votes"
    r = await client.post(url, headers=guests[0].headers, json={"user_id": host.id})
    assert r.json() == {"votes": 1, "votes_needed": 2, "removed": False}

    # Everyone sees the running count; only the voter knows they voted.
    members_url = f"/chats/{reunion['id']}/members"
    for person, voted in ((guests[0], True), (guests[2], False)):
        rows = (await client.get(members_url, headers=person.headers)).json()
        host_row = next(m for m in rows if m["user"]["id"] == host.id)
        assert (host_row["votes_to_remove"], host_row["votes_needed"]) == (1, 2)
        assert host_row["i_voted"] is voted
        assert "voter" not in str(host_row)
    # Changing your mind takes the vote back.
    await client.delete(f"{url}/{host.id}", headers=guests[0].headers)
    rows = (await client.get(members_url, headers=guests[0].headers)).json()
    assert next(m for m in rows if m["user"]["id"] == host.id)["votes_to_remove"] == 0
    await client.post(url, headers=guests[0].headers, json={"user_id": host.id})

    r = await client.post(url, headers=guests[1].headers, json={"user_id": host.id})
    assert r.json()["removed"] is True

    # Out, and can't rejoin.
    r = await client.post(
        f"/chats/{reunion['id']}/messages", headers=host.headers, json={"body": "hi"}
    )
    assert r.status_code == 404
    r = await client.post(f"/chats/{reunion['id']}/join", headers=host.headers)
    assert r.status_code == 403


async def test_feedback_is_only_for_people_who_were_there(client: httpx.AsyncClient) -> None:
    host = await sign_up(client, "Host", ["Radiohead"])
    guest = await sign_up(client, "Guest", ["Radiohead"])
    outsider = await sign_up(client, "Outsider", ["Radiohead"])
    party_id = await _throw_finished_party(client, host, [guest])

    r = await client.post(
        f"/parties/{party_id}/feedback",
        headers=guest.headers,
        json={"user_id": host.id, "would_party_again": True},
    )
    assert r.status_code == 200
    r = await client.post(
        f"/parties/{party_id}/feedback",
        headers=guest.headers,
        json={"user_id": outsider.id, "would_party_again": False},
    )
    assert r.status_code == 404


async def test_host_again_needs_to_have_been_there(client: httpx.AsyncClient) -> None:
    host = await sign_up(client, "Host", ["Radiohead"])
    guest = await sign_up(client, "Guest", ["Radiohead"])
    outsider = await sign_up(client, "Outsider", ["Radiohead"])
    party_id = await _throw_finished_party(client, host, [guest])

    r = await client.post(
        "/parties", headers=guest.headers, json=party_json(source_party_id=party_id)
    )
    assert r.status_code == 201
    r = await client.post(
        "/parties", headers=outsider.headers, json=party_json(source_party_id=party_id)
    )
    assert r.status_code == 403


# --- account -----------------------------------------------------------------


async def test_delete_account(client: httpx.AsyncClient) -> None:
    ana = await sign_up(client, "Ana", ["Radiohead"])
    ben = await sign_up(client, "Ben", ["Radiohead"])

    r = await client.delete("/me", headers=ana.headers)
    assert r.status_code == 204
    assert (await client.get("/me", headers=ana.headers)).status_code == 401
    assert (await client.get("/discover", headers=ben.headers)).json() == []

    suggestions = (
        await client.get("/interests/suggest", params={"q": "radio"}, headers=ben.headers)
    ).json()
    assert suggestions[0]["usage_count"] == 1


async def test_blocked_people_disappear_from_shared_chats(client: httpx.AsyncClient) -> None:
    host = await sign_up(client, "Host", ["Radiohead"])
    ana = await sign_up(client, "Ana", ["Radiohead"])
    ben = await sign_up(client, "Ben", ["Radiohead"])
    party = (await client.post("/parties", headers=host.headers, json=party_json())).json()
    for guest in (ana, ben):
        await match(client, host, guest)
        invite_id = (
            await client.post(
                f"/parties/{party['id']}/invites", headers=host.headers, json={"user_id": guest.id}
            )
        ).json()["id"]
        await client.post(
            f"/invites/{invite_id}/respond", headers=guest.headers, json={"accept": True}
        )

    chat_id = (await client.get("/chats", headers=host.headers)).json()[0]["id"]
    for person, text in ((ana, "from Ana"), (ben, "from Ben")):
        await client.post(f"/chats/{chat_id}/messages", headers=person.headers, json={"body": text})

    await client.post("/blocks", headers=ana.headers, json={"user_id": ben.id})

    def bodies(r: httpx.Response) -> list[str]:
        return [m["body"] for m in r.json()]

    # Neither sees the other; everyone else still sees both.
    r = await client.get(f"/chats/{chat_id}/messages", headers=ana.headers)
    assert bodies(r) == ["from Ana"]
    r = await client.get(f"/chats/{chat_id}/messages", headers=ben.headers)
    assert bodies(r) == ["from Ben"]
    r = await client.get(f"/chats/{chat_id}/messages", headers=host.headers)
    assert bodies(r) == ["from Ana", "from Ben"]


async def test_passed_list_and_changing_your_mind(client: httpx.AsyncClient) -> None:
    me = await sign_up(client, "Me", ["Radiohead"])
    ben = await sign_up(client, "Ben", ["Radiohead"])
    cal = await sign_up(client, "Cal", ["Radiohead"])
    for person in (ben, cal):
        await client.post(
            f"/discover/{person.id}/decision", headers=me.headers, json={"decision": "pass"}
        )

    passed = (await client.get("/discover/passed", headers=me.headers)).json()
    assert [p["user"]["first_name"] for p in passed] == ["Cal", "Ben"]  # newest first
    assert passed[0]["shared_interests"] == ["Radiohead"]

    # Liking from the Passed list works like any like.
    await client.post(f"/discover/{me.id}/decision", headers=ben.headers, json={"decision": "like"})
    r = await client.post(
        f"/discover/{ben.id}/decision", headers=me.headers, json={"decision": "like"}
    )
    assert r.json()["matched"] is True
    passed = (await client.get("/discover/passed", headers=me.headers)).json()
    assert [p["user"]["first_name"] for p in passed] == ["Cal"]


async def test_party_needs_a_pin(client: httpx.AsyncClient) -> None:
    host = await sign_up(client, "Host", ["Radiohead"])
    body = party_json()
    del body["latitude"], body["longitude"]
    r = await client.post("/parties", headers=host.headers, json=body)
    assert r.status_code == 422

    party = (await client.post("/parties", headers=host.headers, json=party_json())).json()
    r = await client.patch(
        f"/parties/{party['id']}", headers=host.headers, json={"latitude": 40.73}
    )
    assert r.status_code == 422
    r = await client.patch(
        f"/parties/{party['id']}",
        headers=host.headers,
        json={"latitude": 40.73, "longitude": -73.99},
    )
    assert r.status_code == 200
