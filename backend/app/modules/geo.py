"""PostGIS helpers shared by services and agent tools. All distances in metres (geography)."""
from __future__ import annotations

from geoalchemy2.shape import from_shape, to_shape
from shapely.geometry import Point
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.models import Ward


def make_point(lat: float, lon: float):
    return from_shape(Point(lon, lat), srid=4326)


def latlon(geom) -> tuple[float, float] | None:
    if geom is None:
        return None
    p = to_shape(geom)
    return (round(p.y, 6), round(p.x, 6))


def pt_sql(lat: float, lon: float):
    return func.ST_SetSRID(func.ST_MakePoint(lon, lat), 4326)


def ward_for(db: Session, lat: float, lon: float) -> Ward | None:
    return db.scalar(select(Ward).where(func.ST_Covers(Ward.geom, pt_sql(lat, lon))))


def in_city(db: Session, lat: float, lon: float, buffer_m: float = 250) -> bool:
    return bool(db.scalar(text(
        "SELECT EXISTS (SELECT 1 FROM wards WHERE ST_DWithin(geom::geography, "
        "ST_SetSRID(ST_MakePoint(:lon,:lat),4326)::geography, :buf))"
    ), {"lat": lat, "lon": lon, "buf": buffer_m}))


def distance_m(a: tuple[float, float], b: tuple[float, float]) -> float:
    """Haversine (no DB round trip). a, b = (lat, lon)."""
    from math import asin, cos, radians, sin, sqrt

    lat1, lon1, lat2, lon2 = map(radians, (a[0], a[1], b[0], b[1]))
    h = sin((lat2 - lat1) / 2) ** 2 + cos(lat1) * cos(lat2) * sin((lon2 - lon1) / 2) ** 2
    return 2 * 6371000 * asin(sqrt(h))


def within(col, lat: float, lon: float, radius_m: float):
    """SQL predicate: geometry column within radius of point."""
    return func.ST_DWithin(func.Geography(col), func.Geography(pt_sql(lat, lon)), radius_m)


def dist_expr(col, lat: float, lon: float):
    return func.ST_Distance(func.Geography(col), func.Geography(pt_sql(lat, lon)))
