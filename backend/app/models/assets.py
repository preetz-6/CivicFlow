from datetime import date, datetime

from geoalchemy2 import Geometry
from sqlalchemy import ARRAY, Date, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models._types import TZ, AnyGeom, Point, ts_default


class Asset(Base):
    __tablename__ = "assets"
    id: Mapped[str] = mapped_column(String(32), primary_key=True)  # STREETLIGHT-W12-00871
    type: Mapped[str] = mapped_column(String(16), index=True)  # STREETLIGHT|DRAIN|TRANSFORMER|WATER_MAIN|ROAD
    name: Mapped[str | None]
    location = mapped_column(Point(), nullable=False)
    ward_id: Mapped[str | None] = mapped_column(ForeignKey("wards.id"))
    owner: Mapped[str] = mapped_column(String(10), default="MUNICIPAL")
    condition: Mapped[str] = mapped_column(String(10), default="OK")  # OK|FAULTY|POOR
    feeder: Mapped[str | None]  # electrical feeder id for streetlights


class AssetEvent(Base):
    __tablename__ = "asset_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    asset_id: Mapped[str] = mapped_column(ForeignKey("assets.id"), index=True)
    type: Mapped[str] = mapped_column(String(10))  # COMPLAINT | REPAIR
    date: Mapped[datetime] = mapped_column(TZ)
    note: Mapped[str | None] = mapped_column(Text)
    sr_id: Mapped[str | None]
    crew_id: Mapped[str | None]


class PlannedWork(Base):
    __tablename__ = "planned_works"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str]
    agency: Mapped[str] = mapped_column(String(16))
    geom = mapped_column(AnyGeom(), nullable=False)
    start: Mapped[date] = mapped_column(Date)
    end: Mapped[date] = mapped_column(Date)
    note: Mapped[str | None] = mapped_column(Text)


class SensitivePlace(Base):
    __tablename__ = "sensitive_places"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str]
    type: Mapped[str] = mapped_column(String(12))  # SCHOOL|HOSPITAL|MARKET|BUS_STAND|METRO|TEMPLE
    location = mapped_column(Point(), nullable=False)


class KnownRoadFeature(Base):
    __tablename__ = "known_road_features"
    id: Mapped[int] = mapped_column(primary_key=True)
    type: Mapped[str] = mapped_column(String(16))  # SPEED_BREAKER | RAIL_CROSSING
    name: Mapped[str | None]
    location = mapped_column(Point(), nullable=False)


class RoadSegment(Base):
    __tablename__ = "road_segments"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str]
    road_class: Mapped[str] = mapped_column(String(10))  # ARTERIAL | LOCAL
    geom = mapped_column(Geometry("LINESTRING", srid=4326, spatial_index=True), nullable=False)


class Crew(Base):
    __tablename__ = "crews"
    id: Mapped[str] = mapped_column(String(12), primary_key=True)  # W12-A
    name: Mapped[str]
    ward_id: Mapped[str] = mapped_column(ForeignKey("wards.id"))
    skills: Mapped[list[str]] = mapped_column(ARRAY(String))  # ROADS, ELECTRICAL, DRAINS, SWM, TREES
    capacity: Mapped[int] = mapped_column(Integer, default=4)
    base_location = mapped_column(Point(), nullable=False)
    contractor: Mapped[str | None]
    audit_priority: Mapped[str] = mapped_column(String(8), default="NORMAL")  # NORMAL | HIGH


class Inventory(Base):
    __tablename__ = "inventory"
    item: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str]
    qty: Mapped[float] = mapped_column(Float)
    unit: Mapped[str] = mapped_column(String(8))
    out_since: Mapped[datetime | None] = mapped_column(TZ)
    updated_at: Mapped[datetime] = mapped_column(TZ, default=ts_default)
