"""Append-only tables. UPDATE/DELETE on status_events and audit_log are blocked by a DB trigger."""
from datetime import datetime

from sqlalchemy import BigInteger, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models._types import TZ, Json, ts_default


class StatusEvent(Base):
    __tablename__ = "status_events"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    object_type: Mapped[str] = mapped_column(String(4), index=True)  # SR | WO
    object_id: Mapped[str] = mapped_column(String(20), index=True)
    from_state: Mapped[str | None] = mapped_column(String(16))
    to_state: Mapped[str] = mapped_column(String(16))
    actor_type: Mapped[str] = mapped_column(String(8))  # HUMAN | AGENT | SYSTEM
    actor: Mapped[str]  # "user:12" | "agent:investigator" | "system:sla"
    actor_label: Mapped[str | None]  # human-readable, for the citizen timeline
    reason: Mapped[str | None] = mapped_column(Text)
    meta: Mapped[dict | None] = mapped_column(Json)
    at: Mapped[datetime] = mapped_column(TZ, default=ts_default, index=True)


class AuditLog(Base):
    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    actor: Mapped[str]
    action: Mapped[str] = mapped_column(String(48))
    object: Mapped[str] = mapped_column(String(48), index=True)  # "SR:SR-2026-000123"
    before_json: Mapped[dict | None] = mapped_column(Json)
    after_json: Mapped[dict | None] = mapped_column(Json)
    at: Mapped[datetime] = mapped_column(TZ, default=ts_default)


class EventRow(Base):
    __tablename__ = "events"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    name: Mapped[str] = mapped_column(String(48), index=True)
    payload: Mapped[dict] = mapped_column(Json)
    at: Mapped[datetime] = mapped_column(TZ, default=ts_default, index=True)


class Timeline(Base):
    """Citizen-facing plain-language timeline entries (agent actions included)."""

    __tablename__ = "timeline_entries"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    sr_id: Mapped[str] = mapped_column(String(20), index=True)
    stage: Mapped[str] = mapped_column(String(32))
    remarks: Mapped[str] = mapped_column(Text)
    remarks_kn: Mapped[str | None] = mapped_column(Text)
    actor_type: Mapped[str] = mapped_column(String(8))
    public: Mapped[bool] = mapped_column(default=True)
    at: Mapped[datetime] = mapped_column(TZ, default=ts_default)
