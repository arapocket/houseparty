"""Test setup.

Tests run against a real Postgres database called houseparty_test, which is
emptied before every test. A real database (not SQLite, not mocks) because
Discover's distance maths and the uniqueness rules live in Postgres.
"""

import os

# Must happen before anything imports app.config.
os.environ["DATABASE_URL"] = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://houseparty:houseparty@localhost:5432/houseparty_test",
)
os.environ["ENV"] = "test"

from collections.abc import AsyncIterator  # noqa: E402
from datetime import date  # noqa: E402

import httpx  # noqa: E402
import pytest  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.db import Base, engine  # noqa: E402
from app.main import app  # noqa: E402

TEST_CODE = "123456"


@pytest.fixture(scope="session", autouse=True)
async def schema() -> AsyncIterator[None]:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield
    await engine.dispose()


@pytest.fixture(autouse=True)
async def empty_tables(monkeypatch: pytest.MonkeyPatch) -> None:
    tables = ", ".join(t.name for t in Base.metadata.sorted_tables)
    async with engine.begin() as conn:
        await conn.execute(text(f"TRUNCATE {tables} CASCADE"))
    # Every texted code is 123456 in tests.
    monkeypatch.setattr("app.services.auth.generate_code", lambda: TEST_CODE)


@pytest.fixture
async def client() -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


class Person:
    """A signed-up, onboarded test user and their auth header."""

    def __init__(self, id: str, name: str, headers: dict[str, str]):
        self.id = id
        self.name = name
        self.headers = headers


_phone_counter = iter(range(1000, 9999))


async def sign_up(
    client: httpx.AsyncClient,
    name: str,
    interests: list[str],
    *,
    lat: float = 40.7128,
    lon: float = -74.0060,
    birthdate: date = date(1995, 5, 17),
) -> Person:
    phone = f"+1415555{next(_phone_counter)}"
    r = await client.post("/auth/phone/start", json={"phone": phone})
    assert r.status_code == 200, r.text
    r = await client.post("/auth/phone/verify", json={"phone": phone, "code": TEST_CODE})
    assert r.status_code == 200, r.text
    headers = {"Authorization": f"Bearer {r.json()['access_token']}"}

    r = await client.patch(
        "/me",
        headers=headers,
        json={
            "first_name": name,
            "birthdate": birthdate.isoformat(),
            "latitude": lat,
            "longitude": lon,
            "neighborhood": "Somewhere",
        },
    )
    assert r.status_code == 200, r.text
    r = await client.put("/me/interests", headers=headers, json={"interests": interests})
    assert r.status_code == 200, r.text
    return Person(r.json()["id"], name, headers)


async def match(client: httpx.AsyncClient, a: Person, b: Person) -> None:
    r = await client.post(
        f"/discover/{b.id}/decision", headers=a.headers, json={"decision": "like"}
    )
    assert r.status_code == 200, r.text
    r = await client.post(
        f"/discover/{a.id}/decision", headers=b.headers, json={"decision": "like"}
    )
    assert r.json()["matched"] is True, r.text
