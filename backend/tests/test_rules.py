"""The small pure functions the product rules rest on. No database needed."""

import uuid
from datetime import date

import pytest

from app.schemas import clean_phone
from app.services.chat import votes_needed
from app.services.geo import display_distance_km, haversine_km
from app.services.interests import is_acceptable, normalize_interest
from app.services.matching import age_on, meets_minimum_age, ordered_pair


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("  Radiohead!! ", "radiohead"),
        ("RADIOHEAD", "radiohead"),
        ("Kid   A  era Radiohead", "kid a era radiohead"),
        ("Drum & Bass", "drum & bass"),
        ("C++", "c++"),
        ("hip-hop", "hip-hop"),
        ("90s R&B", "90s r&b"),
        ("Café", "café"),
        ("ｆｕｌｌｗｉｄｔｈ", "fullwidth"),  # NFKC folds lookalike characters
    ],
)
def test_normalize_interest(raw: str, expected: str) -> None:
    assert normalize_interest(raw) == expected


def test_normalize_makes_spellings_collide() -> None:
    assert normalize_interest("Kid A-era Radiohead!") != normalize_interest("radiohead")
    assert normalize_interest("Board Games.") == normalize_interest("board games")


def test_is_acceptable() -> None:
    assert is_acceptable("radiohead")
    assert not is_acceptable("a")
    assert not is_acceptable("")
    assert not is_acceptable("x" * 41)


@pytest.mark.parametrize(
    ("others", "needed"),
    [(0, 0), (1, 0), (2, 2), (3, 2), (4, 3), (5, 3), (10, 6)],
)
def test_votes_needed(others: int, needed: int) -> None:
    assert votes_needed(others) == needed


def test_age_on_birthday_boundary() -> None:
    born = date(2005, 9, 24)
    assert age_on(born, date(2026, 9, 23)) == 20
    assert age_on(born, date(2026, 9, 24)) == 21


def test_meets_minimum_age() -> None:
    assert meets_minimum_age(date(2005, 9, 24), date(2026, 9, 24))
    assert not meets_minimum_age(date(2005, 9, 25), date(2026, 9, 24))


def test_leap_day_birthday() -> None:
    born = date(2004, 2, 29)
    assert age_on(born, date(2025, 2, 28)) == 20
    assert age_on(born, date(2025, 3, 1)) == 21


def test_ordered_pair_is_order_independent() -> None:
    a, b = uuid.uuid4(), uuid.uuid4()
    assert ordered_pair(a, b) == ordered_pair(b, a)


def test_distance_is_never_precise() -> None:
    assert display_distance_km(0.2) == 1  # never "0 km away"
    assert display_distance_km(3.4) == 3
    assert isinstance(display_distance_km(12.71), int)


def test_haversine_roughly_right() -> None:
    # Manhattan to Brooklyn Bridge Park is a few km.
    km = haversine_km(40.7580, -73.9855, 40.7003, -73.9967)
    assert 6 < km < 7


def test_clean_phone() -> None:
    assert clean_phone("+1 (415) 555-0100") == "+14155550100"
    with pytest.raises(ValueError):
        clean_phone("415 555 0100")  # no country code
