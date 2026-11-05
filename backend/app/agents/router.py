"""Agent Activity Log API."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.core import scope
from app.core.actor import Actor
from app.core.clock import now
from app.core.db import get_db
from app.core.security import require_roles
from app.models import AgentRun, User
from app.models.enums import Role
from app.modules.complaints.serialize import run_summary

router = APIRouter(tags=["agents"])
LABELS = {"investigator": "Case Investigator", "followup": "Follow-up & Escalation", "sensing": "Road Hazard Sensing",
          "auditor": "Evidence Auditor", "surge": "Surge Commander"}


def row(db: Session, r: AgentRun, users: dict) -> dict:
    return {"id": r.id, "at": r.started_at, "agent": r.agent, "agent_label": LABELS.get(r.agent, r.agent),
            "trigger": r.trigger, "subject_type": r.subject_type, "subject_id": r.subject_id, "decision": r.decision,
            "confidence": r.confidence, "model": r.model, "mode": "rules" if r.model == "rules" else "model",
            "status": r.status, "latency_ms": r.latency_ms, "overridden": r.overridden_by is not None,
            "overridden_by": users.get(r.overridden_by), "override_reason": r.override_reason,
            "accepted": r.accepted_by is not None}


@router.get("/agent-runs")
def list_runs(agent: str | None = None, subject_id: str | None = None, overridden: bool | None = None,
              page: int = 1, page_size: int = 20, db: Session = Depends(get_db),
              actor: Actor = Depends(require_roles(Role.CONTROL_ROOM, Role.WARD_OFFICER))):
    q = select(AgentRun)
    if agent:
        q = q.where(AgentRun.agent == agent)
    if subject_id:
        if actor.role == Role.WARD_OFFICER and not scope.can_access_sr(db, actor, subject_id):
            raise HTTPException(403, "Not your ward")
        q = q.where(AgentRun.subject_id == subject_id)
    elif actor.role == Role.WARD_OFFICER:
        raise HTTPException(403, "The city-wide Activity Log is for the Control Room")
    if overridden is not None:
        q = q.where(AgentRun.overridden_by.is_not(None) if overridden else AgentRun.overridden_by.is_(None))
    total = db.scalar(select(func.count()).select_from(q.subquery()))
    runs = db.scalars(q.order_by(AgentRun.id.desc()).offset((page - 1) * page_size).limit(min(page_size, 100))).all()
    users = dict(db.execute(select(User.id, User.name)).all())
    return {"items": [row(db, r, users) for r in runs], "total": total, "page": page, "page_size": page_size}


@router.get("/agent-runs/{run_id}")
def get_run(run_id: int, db: Session = Depends(get_db),
            actor: Actor = Depends(require_roles(Role.CONTROL_ROOM, Role.WARD_OFFICER))):
    r = db.get(AgentRun, run_id)
    if r is None:
        raise HTTPException(404)
    if actor.role == Role.WARD_OFFICER and not (r.subject_type == "SR" and scope.can_access_sr(db, actor, r.subject_id)):
        raise HTTPException(403)
    return {**run_summary(db, r), "trigger": r.trigger, "subject_type": r.subject_type, "subject_id": r.subject_id,
            "input": r.input_summary, "error": r.error, "agent_label": LABELS.get(r.agent, r.agent)}


class OverrideIn(BaseModel):
    reason: str = Field(min_length=5)


@router.post("/agent-runs/{run_id}/override")
def override_run(run_id: int, body: OverrideIn, db: Session = Depends(get_db),
                 actor: Actor = Depends(require_roles(Role.CONTROL_ROOM, Role.WARD_OFFICER))):
    """Record that a human disagreed with this System Suggestion (shown in the Activity Log)."""
    r = db.get(AgentRun, run_id)
    if r is None:
        raise HTTPException(404)
    r.overridden_by, r.override_reason, r.overridden_at = actor.user_id, body.reason, now()
    db.commit()
    return {"ok": True}


@router.get("/agent-stats")
def stats(db: Session = Depends(get_db), actor: Actor = Depends(require_roles(Role.CONTROL_ROOM))):
    rows = db.execute(select(AgentRun.agent, func.count(), func.count(AgentRun.overridden_by),
                             func.sum(case((AgentRun.model == "rules", 1), else_=0)), func.avg(AgentRun.latency_ms))
                      .group_by(AgentRun.agent)).all()
    return [{"agent": a, "agent_label": LABELS.get(a, a), "runs": n, "overridden": o, "rules_runs": int(rr or 0),
             "avg_latency_ms": int(lat or 0)} for a, n, o, rr, lat in rows]
