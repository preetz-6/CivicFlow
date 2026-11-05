"""SLA rule engine (deterministic). Runs on the scheduler.

- recompute sla_state; publish sla.at_risk / sla.breached on change (Agent 2 listens)
- on breach: escalate one level automatically (L1..L4); further levels each 50% of the SLA overdue
- escalation NEVER moves sla_due_at / sla_started_at
- second reopen -> automatic L2
- RESOLVED past the verification window -> CLOSED (closure_type AUTO), counted separately
"""
from __future__ import annotations

import logging
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.actor import Actor
from app.core.bus import Event, bus
from app.core.clock import now
from app.core.db import session_scope
from app.models import Escalation, ServiceRequest, Timeline, User
from app.models.enums import Role, SLAState
from app.modules.notifications.service import notify_citizen, notify_staff
from app.modules.sla.service import compute
from app.modules.workflow.service import transition

log = logging.getLogger("civicflow.sla")
MAX_LEVEL = 4
LEVEL_TITLE = {1: "Ward Officer", 2: "Zonal Officer", 3: "Executive Engineer", 4: "Commissioner"}
OPEN = ["SUBMITTED", "ASSIGNED", "IN_PROGRESS", "WORK_COMPLETED", "VERIFIED", "ON_HOLD", "REOPENED"]


def authority_for(db: Session, sr: ServiceRequest, level: int) -> User | None:
    if level <= 1:
        return db.get(User, sr.owner_id) if sr.owner_id else None
    if level == 2:
        return db.scalar(select(User).where(User.role == Role.WARD_OFFICER, User.ward_id.is_(None)).order_by(User.id))
    return db.scalar(select(User).where(User.role == Role.CONTROL_ROOM).order_by(User.id))


def escalate(db: Session, sr: ServiceRequest, level: int, trigger: str, reason_summary: str,
             agent_run_id: int | None = None) -> Escalation | None:
    level = min(level, MAX_LEVEL)
    if level <= (sr.escalation_level or 0):
        return None
    due_before, start_before = sr.sla_due_at, sr.sla_started_at
    auth = authority_for(db, sr, level)
    e = Escalation(sr_id=sr.id, level=level, trigger=trigger, reason_summary=reason_summary,
                   authority_id=auth.id if auth else None, agent_run_id=agent_run_id, created_at=now(),
                   deadline=now() + timedelta(hours=24))
    db.add(e)
    sr.escalation_level = level
    assert sr.sla_due_at == due_before and sr.sla_started_at == start_before  # never resets the clock
    db.add(Timeline(sr_id=sr.id, stage=f"Escalated to L{level}",
                    remarks=f"Escalated to the {LEVEL_TITLE[level]}. {reason_summary}",
                    remarks_kn=f"{LEVEL_TITLE[level]} ಅವರಿಗೆ ಹೆಚ್ಚಿನ ಕ್ರಮಕ್ಕಾಗಿ ಕಳುಹಿಸಲಾಗಿದೆ. {reason_summary}",
                    actor_type="SYSTEM"))
    if auth:
        notify_staff(db, auth.id, "ESCALATION", f"{sr.id} escalated to L{level} ({trigger}): {reason_summary}", sr.id)
    db.flush()
    bus.publish(db, "complaint.escalated", {"id": sr.id, "level": level, "trigger": trigger, "escalation_id": e.id})
    return e


def _breach_level(sr: ServiceRequest, remaining_s: float) -> int:
    """L1 at breach, +1 for every further 50% of the allowed time overdue."""
    allowed = (sr.sla_due_at - sr.sla_started_at).total_seconds()
    overdue = -remaining_s
    return min(MAX_LEVEL, 1 + int(overdue // (0.5 * allowed))) if allowed > 0 else 1


def sweep(db: Session) -> dict:
    stats = {"at_risk": 0, "breached": 0, "escalated": 0, "auto_closed": 0}
    for sr in db.scalars(select(ServiceRequest).where(ServiceRequest.status.in_(OPEN),
                                                      ServiceRequest.sla_due_at.is_not(None))):
        v = compute(sr)
        if v.state and v.state != sr.sla_state:
            prev, sr.sla_state = sr.sla_state, v.state
            if v.state == SLAState.AT_RISK:
                stats["at_risk"] += 1
                bus.publish(db, "sla.at_risk", {"id": sr.id, "fraction": round(v.fraction or 0, 3), "prev": prev})
            elif v.state == SLAState.BREACHED:
                stats["breached"] += 1
                bus.publish(db, "sla.breached", {"id": sr.id, "prev": prev})
        if v.state == SLAState.BREACHED:
            target = _breach_level(sr, v.remaining_s)
            if target > (sr.escalation_level or 0):
                hours = abs(v.remaining_s) / 3600
                e = escalate(db, sr, (sr.escalation_level or 0) + 1, "SLA_BREACH",
                             f"Resolution deadline crossed by {hours:.0f} h. Cause being analysed.")
                stats["escalated"] += bool(e)
    for sr in db.scalars(select(ServiceRequest).where(ServiceRequest.status == "RESOLVED",
                                                      ServiceRequest.verification_due_at.is_not(None),
                                                      ServiceRequest.verification_due_at < now())):
        transition(db, sr, "CLOSED", Actor.system("auto_close"), closure_type="AUTO",
                   reason="Verification window expired without citizen response")
        stats["auto_closed"] += 1
    return stats


def run_sweep() -> None:
    try:
        with session_scope() as db:
            s = sweep(db)
            if any(s.values()):
                log.info("sla sweep %s", s)
    except Exception:
        log.exception("sla sweep failed")


def on_reopened(ev: Event) -> None:
    with session_scope() as db:
        sr = db.get(ServiceRequest, ev.payload["id"])
        if sr and sr.reopen_count >= 2 and sr.escalation_level < 2:
            escalate(db, sr, 2, "REOPEN", f"Reopened {sr.reopen_count} times by the citizen.")


def register() -> None:
    from app import scheduler

    bus.subscribe("complaint.reopened", on_reopened)
    scheduler.add_job("sla_sweep", run_sweep, 15)
