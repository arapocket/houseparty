"""Fill the dev database with people to look at.

    uv run python -m scripts.seed          add the seed people (skips if already there)
    uv run python -m scripts.seed --reset  empty every table first

Creates "You" plus a dozen neighbours with overlapping interests, a couple of
matches, and a party, then prints a token so you can call the API as "You"
straight away:

    curl -H "Authorization: Bearer <token>" localhost:8000/discover

Everyone lives around Lower Manhattan. Change CENTER to move them.
"""

from __future__ import annotations

import asyncio
import random
import sys
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select, text

from app.db import Base, SessionFactory
from app.models import Decision, Match, User
from app.schemas import ProfileIn
from app.security import create_access_token
from app.services import parties, profiles
from app.services.matching import ordered_pair

CENTER = (40.7209, -74.0007)  # SoHo

PEOPLE: list[tuple[str, str, list[str]]] = [
    ("You", "SoHo", ["Kid A era Radiohead", "Board games", "Natural wine", "Bouldering", "Ramen"]),
    ("Maya", "Tribeca", ["Kid A era Radiohead", "Natural wine", "Film photography"]),
    ("Jonah", "West Village", ["Board games", "Bouldering", "Sci-fi novels"]),
    ("Priya", "Chinatown", ["Ramen", "Natural wine", "Board games", "Karaoke"]),
    ("Leo", "East Village", ["Kid A era Radiohead", "Synths", "Vinyl"]),
    ("Sam", "Lower East Side", ["Bouldering", "Ramen", "Trail running"]),
    ("Ines", "Nolita", ["Film photography", "Vinyl", "Natural wine"]),
    ("Theo", "Greenwich Village", ["Board games", "D&D", "Sci-fi novels"]),
    ("Rosa", "Williamsburg", ["Karaoke", "Ramen", "Salsa dancing"]),
    ("Kenji", "DUMBO", ["Kid A era Radiohead", "Bouldering", "Board games", "Ramen"]),
    ("Ava", "Financial District", ["Trail running", "Natural wine"]),
    ("Omar", "Chelsea", ["Synths", "Vinyl", "Karaoke"]),
    ("Far Away Fran", "Philadelphia", ["Kid A era Radiohead", "Board games"]),
]


def near_center(rng: random.Random, km: float) -> tuple[float, float]:
    # Roughly: 1 degree of latitude is 111 km; longitude a bit less up here.
    return (
        CENTER[0] + rng.uniform(-km, km) / 111,
        CENTER[1] + rng.uniform(-km, km) / 85,
    )


async def main(reset: bool) -> None:
    rng = random.Random(42)  # same "random" people every time
    async with SessionFactory() as session:
        if reset:
            tables = ", ".join(t.name for t in Base.metadata.sorted_tables)
            await session.execute(text(f"TRUNCATE {tables} CASCADE"))

        if await session.scalar(select(User).where(User.phone == "+15550000000")):
            print("Already seeded. Use --reset to start over.")
            return

        users: dict[str, User] = {}
        for i, (name, hood, interests) in enumerate(PEOPLE):
            lat, lon = (39.9526, -75.1652) if hood == "Philadelphia" else near_center(rng, 6)
            user = User(
                phone=f"+1555000{i:04d}",
                phone_verified_at=datetime.now(UTC),
                interests=[],
            )
            session.add(user)
            await session.flush()
            await profiles.update_profile(
                session,
                user,
                ProfileIn(
                    first_name=name,
                    birthdate=date(1990 + i % 8, 1 + i % 12, 1 + i),
                    neighborhood=hood,
                    bio=f"{name} from {hood}.",
                    latitude=lat,
                    longitude=lon,
                    search_radius_km=15,
                    down_to_party=i % 3 != 0,
                ),
            )
            await profiles.set_interests(session, user, interests)
            users[name] = user

        # "You" has matched with Maya and Kenji, and Priya already likes you.
        you = users["You"]
        for name in ("Maya", "Kenji"):
            other = users[name]
            session.add(Decision(actor_id=you.id, target_id=other.id, decision="like"))
            session.add(Decision(actor_id=other.id, target_id=you.id, decision="like"))
            low, high = ordered_pair(you.id, other.id)
            session.add(Match(user_low_id=low, user_high_id=high))
        session.add(Decision(actor_id=users["Priya"].id, target_id=you.id, decision="like"))

        party = await parties.create_party(
            session,
            you,
            title="Kid A front to back",
            description="Lights off, good speakers, natural wine.",
            starts_at=datetime.now(UTC) + timedelta(days=5),
            ends_at=None,
            neighborhood="SoHo",
            address="123 Example St, Apt 5",
            latitude=CENTER[0],
            longitude=CENTER[1],
            interests=["Kid A era Radiohead", "Natural wine"],
        )
        invite = await parties.invite(session, you, party, users["Maya"].id)
        await parties.respond_to_invite(session, users["Maya"], invite, accept=True)
        await parties.invite(session, you, party, users["Kenji"].id)

        await session.commit()
        print(f"Seeded {len(users)} people. Sign in as You with:\n")
        print(f"  Authorization: Bearer {create_access_token(you.id)}\n")


if __name__ == "__main__":
    asyncio.run(main(reset="--reset" in sys.argv))
