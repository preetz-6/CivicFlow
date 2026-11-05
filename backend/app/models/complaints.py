from datetime import datetime, timedelta

from sqlalchemy import BigInteger, Boolean, Float, ForeignKey, Integer, Interval, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models._types import TZ, Json, Point, ts_default


class SlaPolicy(Base):
    __tablename__ = "sla_policies"
    __table_args__ = (UniqueConstraint("category", "priority"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    category: Mapped[str] = mapped_column(String(24))
    priority: Mapped[str] = mapped_column(String(2))
    resolution_hours: Mapped[float]
    verification_hours: Mapped[float]
    description: Mapped[str | None]


class ServiceRequest(Base):
    __tablename__ = "service_requests"
    id: Mapped[str] = mapped_column(String(20), primary_key=True)  # SR-2026-000123
    tracking_code: Mapped[str] = mapped_column(String(12), unique=True, index=True)
    category: Mapped[str] = mapped_column(String(24), index=True)
    citizen_category: Mapped[str | None] = mapped_column(String(24))  # what the citizen picked
    description: Mapped[str] = mapped_column(Text)
    location = mapped_column(Point(), nullable=False)
    address: Mapped[str | None]
    landmark: Mapped[str | None]
    ward_id: Mapped[str | None] = mapped_column(ForeignKey("wards.id"), index=True)
    department_id: Mapped[str | None] = mapped_column(ForeignKey("departments.id"))
    asset_id: Mapped[str | None] = mapped_column(ForeignKey("assets.id"))
    status: Mapped[str] = mapped_column(String(16), index=True)
    prev_status: Mapped[str | None] = mapped_column(String(16))  # for ON_HOLD resume
    hold_reason: Mapped[str | None] = mapped_column(String(16))
    priority: Mapped[str] = mapped_column(String(2), default="P3")
    priority_score: Mapped[float] = mapped_column(Float, default=0.0)
    owner_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True)
    parent_sr_id: Mapped[str | None] = mapped_column(ForeignKey("service_requests.id"))
    reporter_count: Mapped[int] = mapped_column(Integer, default=1)
    source: Mapped[str] = mapped_column(String(16), default="CITIZEN_WEB")
    incident_id: Mapped[int | None] = mapped_column(ForeignKey("incidents.id"))
    escalation_level: Mapped[int] = mapped_column(Integer, default=0)
    sla_policy_id: Mapped[int | None] = mapped_column(ForeignKey("sla_policies.id"))
    sla_started_at: Mapped[datetime | None] = mapped_column(TZ)
    sla_due_at: Mapped[datetime | None] = mapped_column(TZ)  # base due; effective = due + paused_total
    sla_paused_total: Mapped[timedelta] = mapped_column(Interval, default=timedelta(0))
    sla_paused_at: Mapped[datetime | None] = mapped_column(TZ)
    sla_state: Mapped[str | None] = mapped_column(String(10))
    verification_due_at: Mapped[datetime | None] = mapped_column(TZ)
    closure_type: Mapped[str | None] = mapped_column(String(8))
    reopen_count: Mapped[int] = mapped_column(Integer, default=0)
    rejection_reason_code: Mapped[str | None]
    rejection_explanation: Mapped[str | None] = mapped_column(Text)
    corroboration_count: Mapped[int] = mapped_column(Integer, default=0)  # distinct vehicles
    emergency: Mapped[bool] = mapped_column(Boolean, default=False)
    citizen_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    contact_name: Mapped[str | None]
    contact_phone: Mapped[str | None]  # never serialised to FIELD_TEAM
    anonymous: Mapped[bool] = mapped_column(Boolean, default=False)
    language: Mapped[str] = mapped_column(String(2), default="en")
    created_at: Mapped[datetime] = mapped_column(TZ, default=ts_default, index=True)
    updated_at: Mapped[datetime] = mapped_column(TZ, default=ts_default, onupdate=ts_default)
    resolved_at: Mapped[datetime | None] = mapped_column(TZ)
    closed_at: Mapped[datetime | None] = mapped_column(TZ)


class SrReporter(Base):
    __tablename__ = "sr_reporters"
    id: Mapped[int] = mapped_column(primary_key=True)
    sr_id: Mapped[str] = mapped_column(ForeignKey("service_requests.id"), index=True)
    citizen_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    contact_name: Mapped[str | None]
    contact_phone: Mapped[str | None]
    language: Mapped[str] = mapped_column(String(2), default="en")
    merged_from_sr_id: Mapped[str | None] = mapped_column(ForeignKey("service_requests.id"))
    added_at: Mapped[datetime] = mapped_column(TZ, default=ts_default)


class Attachment(Base):
    __tablename__ = "attachments"
    id: Mapped[int] = mapped_column(primary_key=True)
    sr_id: Mapped[str | None] = mapped_column(ForeignKey("service_requests.id"), index=True)
    wo_id: Mapped[str | None] = mapped_column(ForeignKey("work_orders.id"), index=True)
    kind: Mapped[str] = mapped_column(String(8))
    path: Mapped[str]
    content_type: Mapped[str] = mapped_column(String(48), default="image/jpeg")
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    phash: Mapped[str | None] = mapped_column(String(32))
    exif_lat: Mapped[float | None]
    exif_lon: Mapped[float | None]
    exif_time: Mapped[datetime | None] = mapped_column(TZ)
    uploaded_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    uploaded_at: Mapped[datetime] = mapped_column(TZ, default=ts_default)


class Feedback(Base):
    __tablename__ = "feedback"
    id: Mapped[int] = mapped_column(primary_key=True)
    sr_id: Mapped[str] = mapped_column(ForeignKey("service_requests.id"), index=True)
    rating: Mapped[int | None]
    comment: Mapped[str | None] = mapped_column(Text)
    reopen_reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(TZ, default=ts_default)


class Referral(Base):
    __tablename__ = "referrals"
    id: Mapped[int] = mapped_column(primary_key=True)
    sr_id: Mapped[str] = mapped_column(ForeignKey("service_requests.id"), index=True)
    agency: Mapped[str] = mapped_column(String(8))  # BESCOM | BWSSB
    reason: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(10), default="DRAFT")  # DRAFT | SENT | CLOSED
    sent_at: Mapped[datetime | None] = mapped_column(TZ)
    followups_sent: Mapped[int] = mapped_column(Integer, default=0)
    last_followup_at: Mapped[datetime | None] = mapped_column(TZ)
    agency_status: Mapped[str] = mapped_column(String(16), default="NO_RESPONSE")  # NO_RESPONSE|ACKNOWLEDGED|IN_PROGRESS|RESOLVED
    agency_reply: Mapped[str | None] = mapped_column(Text)
    agency_replied_at: Mapped[datetime | None] = mapped_column(TZ)
    created_at: Mapped[datetime] = mapped_column(TZ, default=ts_default)


class AgencyMessage(Base):
    """Simulated agency inbox: what we sent, and what the 'agency' replied."""

    __tablename__ = "agency_messages"
    id: Mapped[int] = mapped_column(primary_key=True)
    referral_id: Mapped[int] = mapped_column(ForeignKey("referrals.id"), index=True)
    direction: Mapped[str] = mapped_column(String(4))  # OUT | IN
    body: Mapped[str] = mapped_column(Text)
    at: Mapped[datetime] = mapped_column(TZ, default=ts_default)


class Escalation(Base):
    __tablename__ = "escalations"
    id: Mapped[int] = mapped_column(primary_key=True)
    sr_id: Mapped[str] = mapped_column(ForeignKey("service_requests.id"), index=True)
    level: Mapped[int]
    trigger: Mapped[str] = mapped_column(String(24))  # SLA_BREACH | AGENCY_NO_RESPONSE | REOPEN
    reason_summary: Mapped[str] = mapped_column(Text)
    authority_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    agent_run_id: Mapped[int | None] = mapped_column(ForeignKey("agent_runs.id"))
    created_at: Mapped[datetime] = mapped_column(TZ, default=ts_default)
    deadline: Mapped[datetime | None] = mapped_column(TZ)
    acknowledged_at: Mapped[datetime | None] = mapped_column(TZ)


class ReassignmentProposal(Base):
    __tablename__ = "reassignment_proposals"
    id: Mapped[int] = mapped_column(primary_key=True)
    wo_id: Mapped[str] = mapped_column(ForeignKey("work_orders.id"), index=True)
    from_crew_id: Mapped[str | None] = mapped_column(ForeignKey("crews.id"))
    to_crew_id: Mapped[str] = mapped_column(ForeignKey("crews.id"))
    reason: Mapped[str] = mapped_column(Text)
    distance_km: Mapped[float | None]
    status: Mapped[str] = mapped_column(String(10), default="PENDING")  # PENDING|APPROVED|REJECTED
    agent_run_id: Mapped[int | None] = mapped_column(ForeignKey("agent_runs.id"))
    decided_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    decided_at: Mapped[datetime | None] = mapped_column(TZ)
    created_at: Mapped[datetime] = mapped_column(TZ, default=ts_default)


class MaterialRequest(Base):
    __tablename__ = "material_requests"
    id: Mapped[int] = mapped_column(primary_key=True)
    item: Mapped[str] = mapped_column(ForeignKey("inventory.item"))
    qty: Mapped[float]
    sr_id: Mapped[str | None] = mapped_column(ForeignKey("service_requests.id"))
    wo_id: Mapped[str | None] = mapped_column(ForeignKey("work_orders.id"))
    status: Mapped[str] = mapped_column(String(10), default="RAISED")
    agent_run_id: Mapped[int | None] = mapped_column(ForeignKey("agent_runs.id"))
    created_at: Mapped[datetime] = mapped_column(TZ, default=ts_default)


class Notification(Base):
    __tablename__ = "notifications"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    recipient: Mapped[str]  # "user:12" | phone | "agency:BESCOM"
    recipient_type: Mapped[str] = mapped_column(String(10))  # CITIZEN|OFFICER|FIELD|AGENCY|CONTROL
    channel: Mapped[str] = mapped_column(String(10), default="SMS")
    language: Mapped[str] = mapped_column(String(2), default="en")
    event: Mapped[str] = mapped_column(String(48))
    body: Mapped[str] = mapped_column(Text)
    related_sr_id: Mapped[str | None] = mapped_column(ForeignKey("service_requests.id"), index=True)
    dedupe_key: Mapped[str | None] = mapped_column(String(128), unique=True)
    meta: Mapped[dict | None] = mapped_column(Json)
    created_at: Mapped[datetime] = mapped_column(TZ, default=ts_default, index=True)
