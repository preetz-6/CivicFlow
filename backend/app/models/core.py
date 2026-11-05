from datetime import datetime

from geoalchemy2 import Geometry
from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models._types import TZ, Json, ts_default


class Ward(Base):
    __tablename__ = "wards"
    id: Mapped[str] = mapped_column(String(8), primary_key=True)  # "W12"
    name: Mapped[str]
    name_kn: Mapped[str | None]
    zone: Mapped[str]
    geom = mapped_column(Geometry("MULTIPOLYGON", srid=4326, spatial_index=True), nullable=False)


class Department(Base):
    __tablename__ = "departments"
    id: Mapped[str] = mapped_column(String(16), primary_key=True)  # "ROADS"
    name: Mapped[str]
    name_kn: Mapped[str | None]


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str]
    role: Mapped[str] = mapped_column(String(16), index=True)
    designation: Mapped[str | None]
    ward_id: Mapped[str | None] = mapped_column(ForeignKey("wards.id"))
    zone: Mapped[str | None]
    department_id: Mapped[str | None] = mapped_column(ForeignKey("departments.id"))
    crew_id: Mapped[str | None] = mapped_column(ForeignKey("crews.id", use_alter=True))
    language: Mapped[str] = mapped_column(String(2), default="en")
    phone: Mapped[str | None]
    password_hash: Mapped[str | None] = mapped_column(String(160))  # pbkdf2_sha256$iterations$salt$hash
    created_at: Mapped[datetime] = mapped_column(TZ, default=ts_default)


class SystemState(Base):
    """Small key/value store (clock state, scheduler cursors)."""

    __tablename__ = "system_state"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[dict] = mapped_column(Json)
