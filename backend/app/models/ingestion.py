from datetime import datetime

from sqlalchemy import BigInteger, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models._types import TZ, Json, Point, ts_default


class DataSource(Base):
    __tablename__ = "data_sources"
    id: Mapped[str] = mapped_column(String(24), primary_key=True)  # oem-sim
    name: Mapped[str]
    kind: Mapped[str] = mapped_column(String(16))  # VEHICLE_OEM | CITIZEN_PHOTO
    api_key_hash: Mapped[str] = mapped_column(String(64))
    simulated: Mapped[bool] = mapped_column(default=True)
    last_ingested_at: Mapped[datetime | None] = mapped_column(TZ)
    accepted_count: Mapped[int] = mapped_column(Integer, default=0)
    rejected_count: Mapped[int] = mapped_column(Integer, default=0)


class RawDetection(Base):
    __tablename__ = "raw_detections"
    __table_args__ = (UniqueConstraint("source_id", "source_record_id"),)
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    source_id: Mapped[str] = mapped_column(ForeignKey("data_sources.id"))
    source_record_id: Mapped[str] = mapped_column(String(64))
    location = mapped_column(Point(), nullable=False)
    hazard_type: Mapped[str] = mapped_column(String(16))
    detected_at: Mapped[datetime] = mapped_column(TZ, index=True)
    confidence: Mapped[float] = mapped_column(Float)
    speed_kmph: Mapped[float | None]
    vertical_accel_peak_g: Mapped[float | None]
    vehicle_ref: Mapped[str] = mapped_column(String(64))
    image_url: Mapped[str | None]
    raw_payload: Mapped[dict] = mapped_column(Json)
    cluster_id: Mapped[int | None] = mapped_column(ForeignKey("hazard_clusters.id"), index=True)
    ingested_at: Mapped[datetime] = mapped_column(TZ, default=ts_default, index=True)


class RejectedDetection(Base):
    __tablename__ = "rejected_detections"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    source_id: Mapped[str] = mapped_column(ForeignKey("data_sources.id"))
    source_record_id: Mapped[str | None] = mapped_column(String(64))
    reason: Mapped[str] = mapped_column(String(160))
    raw_payload: Mapped[dict | None] = mapped_column(Json)
    at: Mapped[datetime] = mapped_column(TZ, default=ts_default)


class IngestIdempotency(Base):
    __tablename__ = "ingest_idempotency"
    key: Mapped[str] = mapped_column(String(96), primary_key=True)  # source_id:Idempotency-Key
    response: Mapped[dict] = mapped_column(Json)
    at: Mapped[datetime] = mapped_column(TZ, default=ts_default)


class HazardCluster(Base):
    __tablename__ = "hazard_clusters"
    id: Mapped[int] = mapped_column(primary_key=True)
    center = mapped_column(Point(), nullable=False)
    hazard_type: Mapped[str] = mapped_column(String(16), default="POTHOLE")
    n_detections: Mapped[int] = mapped_column(Integer)
    distinct_vehicles: Mapped[int] = mapped_column(Integer)
    avg_confidence: Mapped[float] = mapped_column(Float)
    avg_jolt_g: Mapped[float | None] = mapped_column(Float)
    days_seen: Mapped[int] = mapped_column(Integer, default=1)
    first_seen: Mapped[datetime] = mapped_column(TZ)
    last_seen: Mapped[datetime] = mapped_column(TZ)
    status: Mapped[str] = mapped_column(String(16), default="NEW", index=True)
    filter_reason: Mapped[str | None] = mapped_column(String(160))
    decision_reason: Mapped[str | None] = mapped_column(Text)
    road_class: Mapped[str | None] = mapped_column(String(10))
    sr_id: Mapped[str | None] = mapped_column(ForeignKey("service_requests.id"))
    flagged_wo_id: Mapped[str | None] = mapped_column(ForeignKey("work_orders.id"))
    agent_run_id: Mapped[int | None] = mapped_column(ForeignKey("agent_runs.id"))
    created_at: Mapped[datetime] = mapped_column(TZ, default=ts_default)
    updated_at: Mapped[datetime] = mapped_column(TZ, default=ts_default, onupdate=ts_default)
