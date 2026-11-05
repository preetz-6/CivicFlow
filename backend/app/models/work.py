from datetime import datetime

from geoalchemy2 import Geometry
from sqlalchemy import Boolean, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models._types import TZ, Json, Point, ts_default


class WorkOrder(Base):
    __tablename__ = "work_orders"
    id: Mapped[str] = mapped_column(String(20), primary_key=True)  # WO-2026-000045
    sr_id: Mapped[str] = mapped_column(ForeignKey("service_requests.id"), index=True)
    crew_id: Mapped[str] = mapped_column(ForeignKey("crews.id"), index=True)
    asset_id: Mapped[str | None] = mapped_column(ForeignKey("assets.id"))
    scope: Mapped[str] = mapped_column(Text)
    root_cause: Mapped[str | None] = mapped_column(Text)
    est_cost_inr: Mapped[float | None] = mapped_column(Float)
    materials: Mapped[dict | None] = mapped_column(Json)  # {"cold_mix_bitumen": 0.5}
    status: Mapped[str] = mapped_column(String(12), index=True)
    prev_status: Mapped[str | None] = mapped_column(String(12))
    hold_reason: Mapped[str | None] = mapped_column(String(16))
    rework_reason: Mapped[str | None] = mapped_column(Text)
    rework_count: Mapped[int] = mapped_column(Integer, default=0)
    assigned_at: Mapped[datetime] = mapped_column(TZ, default=ts_default)
    started_at: Mapped[datetime | None] = mapped_column(TZ)
    completed_at: Mapped[datetime | None] = mapped_column(TZ)
    verified_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    verified_at: Mapped[datetime | None] = mapped_column(TZ)
    audit_verdict: Mapped[str | None] = mapped_column(String(4))
    audit_score: Mapped[int | None]
    audit_run_id: Mapped[int | None] = mapped_column(ForeignKey("agent_runs.id"))
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))


class Incident(Base):
    __tablename__ = "incidents"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str]
    category: Mapped[str] = mapped_column(String(24))
    area = mapped_column(Geometry("POLYGON", srid=4326), nullable=True)
    center = mapped_column(Point(), nullable=False)
    severity: Mapped[str] = mapped_column(String(8))  # LOW|MEDIUM|HIGH|SEVERE
    status: Mapped[str] = mapped_column(String(8), default="ACTIVE")  # ACTIVE | CLOSED
    report_count: Mapped[int] = mapped_column(Integer, default=0)
    crew_suggestion: Mapped[str | None] = mapped_column(Text)
    advisory_draft: Mapped[str | None] = mapped_column(Text)
    advisory_draft_kn: Mapped[str | None] = mapped_column(Text)
    advisory_published: Mapped[bool] = mapped_column(Boolean, default=False)
    published_at: Mapped[datetime | None] = mapped_column(TZ)
    published_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    summary: Mapped[str | None] = mapped_column(Text)
    summary_at: Mapped[datetime | None] = mapped_column(TZ)
    agent_run_id: Mapped[int | None] = mapped_column(ForeignKey("agent_runs.id"))
    created_at: Mapped[datetime] = mapped_column(TZ, default=ts_default)


class WeatherAlert(Base):
    """Backs the simulated weather adapter."""

    __tablename__ = "weather_alerts"
    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str]
    severity: Mapped[str] = mapped_column(String(8))
    area_name: Mapped[str | None]
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    issued_at: Mapped[datetime] = mapped_column(TZ, default=ts_default)
    expires_at: Mapped[datetime | None] = mapped_column(TZ)
