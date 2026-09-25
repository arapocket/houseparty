"""Distance helpers.

Exact locations never leave the server. Everything a user sees is rounded,
which is both a privacy decision and the reason we can get away with plain
latitude/longitude columns instead of PostGIS.
"""

from __future__ import annotations

import math

from sqlalchemy import Float, func
from sqlalchemy.sql.elements import ColumnElement

EARTH_RADIUS_KM = 6371.0


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    d_lat = p2 - p1
    d_lon = math.radians(lon2 - lon1)
    a = math.sin(d_lat / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(d_lon / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))


def distance_expression(lat_col, lon_col, lat: float, lon: float) -> ColumnElement[float]:
    """The same formula as SQL, so we can filter and sort by distance."""
    return EARTH_RADIUS_KM * func.acos(
        func.least(
            1.0,
            func.cos(func.radians(lat))
            * func.cos(func.radians(lat_col))
            * func.cos(func.radians(lon_col) - func.radians(lon))
            + func.sin(func.radians(lat)) * func.sin(func.radians(lat_col)),
        ).cast(Float)
    )


def display_distance_km(km: float) -> int:
    """What the app shows. Never more precise than a whole kilometre."""
    return max(1, round(km))
