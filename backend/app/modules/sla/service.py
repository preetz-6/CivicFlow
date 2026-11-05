"""SLA arithmetic. Deterministic code only; agents read these results, never write them.

effective_due = sla_due_at + sla_paused_total (+ the current pause, if paused)
Escalation never touches sla_due_at, so it can never reset the clock.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from app.core.clock import now
from app.domain_config import SLA_AT_RISK_FRACTION
from app.models import ServiceRequest
from app.models.enums import SR_TERMINAL, SLAState


@dataclass
class SlaView:
    state: str | None
    due_at: datetime | None  # effective due
    remaining_s: float | None  # negative when breached
    fraction: float | None  # elapsed / allowed, pauses excluded
    label: str  # "2d 4h left" | "Breached by 6h" | "Paused" | "—"


def _fmt(seconds: float) -> str:
    s = abs(int(seconds))
    d, rem = divmod(s, 86400)
    h, rem = divmod(rem, 3600)
    m = rem // 60
    if d:
        return f"{d}d {h}h"
    if h:
        return f"{h}h {m}m"
    return f"{m}m"


def compute(sr: ServiceRequest, at: datetime | None = None) -> SlaView:
    at = at or now()
    if sr.sla_due_at is None or sr.sla_started_at is None:
        return SlaView(None, None, None, None, "—")
    if sr.status in SR_TERMINAL or sr.status in ("RESOLVED",):
        return SlaView(SLAState.STOPPED, sr.sla_due_at, None, None, "Stopped")
    paused = sr.sla_paused_total or timedelta(0)
    current_pause = (at - sr.sla_paused_at) if sr.sla_paused_at else timedelta(0)
    due = sr.sla_due_at + paused + current_pause
    allowed = (sr.sla_due_at - sr.sla_started_at).total_seconds()
    elapsed = (at - sr.sla_started_at - paused - current_pause).total_seconds()
    frac = elapsed / allowed if allowed > 0 else 1.0
    remaining = (due - at).total_seconds()
    if sr.sla_paused_at:
        return SlaView(SLAState.PAUSED, due, remaining, frac, f"Paused ({_fmt(remaining)} left)")
    if remaining < 0:
        return SlaView(SLAState.BREACHED, due, remaining, frac, f"Breached by {_fmt(remaining)}")
    state = SLAState.AT_RISK if frac >= SLA_AT_RISK_FRACTION else SLAState.ON_TRACK
    return SlaView(state, due, remaining, frac, f"{_fmt(remaining)} left")
