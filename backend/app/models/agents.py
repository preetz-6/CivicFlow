from datetime import datetime

from sqlalchemy import Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models._types import TZ, Json, ts_default


class AgentRun(Base):
    __tablename__ = "agent_runs"
    id: Mapped[int] = mapped_column(primary_key=True)
    agent: Mapped[str] = mapped_column(String(24), index=True)
    trigger: Mapped[str] = mapped_column(String(48))
    subject_type: Mapped[str | None] = mapped_column(String(8))  # SR | WO | CLUSTER | INCIDENT
    subject_id: Mapped[str | None] = mapped_column(String(24), index=True)
    input_summary: Mapped[dict | None] = mapped_column(Json)
    status: Mapped[str] = mapped_column(String(10), default="RUNNING")  # RUNNING|OK|FALLBACK|ERROR
    model: Mapped[str | None] = mapped_column(String(48))  # model id | "rules" | "replay:<model>"
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    output: Mapped[dict | None] = mapped_column(Json)
    decision: Mapped[str | None] = mapped_column(String(160))  # one-line summary for the log table
    rationale: Mapped[str | None] = mapped_column(Text)
    confidence: Mapped[float | None] = mapped_column(Float)
    error: Mapped[str | None] = mapped_column(Text)
    overridden_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    override_reason: Mapped[str | None] = mapped_column(Text)
    overridden_at: Mapped[datetime | None] = mapped_column(TZ)
    accepted_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    started_at: Mapped[datetime] = mapped_column(TZ, default=ts_default, index=True)
    finished_at: Mapped[datetime | None] = mapped_column(TZ)


class AgentStep(Base):
    __tablename__ = "agent_steps"
    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("agent_runs.id"), index=True)
    idx: Mapped[int] = mapped_column(Integer)
    tool: Mapped[str] = mapped_column(String(48))
    args: Mapped[dict | None] = mapped_column(Json)
    result_summary: Mapped[dict | list | None] = mapped_column(Json)
    error: Mapped[str | None] = mapped_column(Text)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    at: Mapped[datetime] = mapped_column(TZ, default=ts_default)
