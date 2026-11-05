"""Reassignment proposals from the Follow-up agent. Only an officer can approve (one click)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import scope
from app.core.actor import Actor
from app.core.clock import now
from app.core.db import get_db
from app.core.security import require_roles
from app.models import AuditLog, Crew, MaterialRequest, ReassignmentProposal, ServiceRequest, Timeline, User, WorkOrder
from app.models.enums import Role
from app.modules.notifications.service import notify_citizen, notify_staff

router = APIRouter(tags=["reassignments"])
OFFICERS = (Role.WARD_OFFICER, Role.CONTROL_ROOM)


def out(db, p: ReassignmentProposal) -> dict:
    wo = db.get(WorkOrder, p.wo_id)
    return {"id": p.id, "wo_id": p.wo_id, "sr_id": wo.sr_id if wo else None, "from_crew_id": p.from_crew_id,
            "to_crew_id": p.to_crew_id, "distance_km": p.distance_km, "reason": p.reason, "status": p.status,
            "agent_run_id": p.agent_run_id, "created_at": p.created_at, "decided_at": p.decided_at}


@router.get("/reassignments")
def list_proposals(status: str = "PENDING", db: Session = Depends(get_db), actor: Actor = Depends(require_roles(*OFFICERS))):
    q = select(ReassignmentProposal).where(ReassignmentProposal.status == status).order_by(ReassignmentProposal.id.desc())
    return [out(db, p) for p in db.scalars(q) if scope.can_access_wo(db, actor, p.wo_id)]


class DecideIn(BaseModel):
    note: str | None = None


def _get(db, pid, actor) -> ReassignmentProposal:
    p = db.get(ReassignmentProposal, pid)
    if p is None or p.status != "PENDING":
        raise HTTPException(409, "No pending proposal")
    scope.ensure_wo(db, actor, p.wo_id)
    return p


@router.post("/reassignments/{pid}/approve")
def approve(pid: int, body: DecideIn | None = None, db: Session = Depends(get_db), actor: Actor = Depends(require_roles(*OFFICERS))):
    p = _get(db, pid, actor)
    wo = db.get(WorkOrder, p.wo_id)
    if wo.status not in ("ASSIGNED", "ON_HOLD", "REWORK", "IN_PROGRESS"):
        raise HTTPException(409, f"Work order is {wo.status}")
    before = wo.crew_id
    wo.crew_id = p.to_crew_id
    p.status, p.decided_by, p.decided_at = "APPROVED", actor.user_id, now()
    db.add(AuditLog(actor=actor.id, action="WO.reassign", object=f"WO:{wo.id}", before_json={"crew_id": before},
                    after_json={"crew_id": wo.crew_id, "proposal_id": p.id, "note": (body.note if body else None)}, at=now()))
    sr = db.get(ServiceRequest, wo.sr_id)
    db.add(Timeline(sr_id=sr.id, stage="Crew Reassigned",
                    remarks=f"Your work has been moved to a nearby crew with free capacity ({p.distance_km} km away) so it can start sooner.",
                    remarks_kn="ಕೆಲಸ ಬೇಗ ಆರಂಭವಾಗಲು ಹತ್ತಿರದ ಇನ್ನೊಂದು ತಂಡಕ್ಕೆ ವಹಿಸಲಾಗಿದೆ.", actor_type="HUMAN", at=now()))
    notify_citizen(db, sr, "DELAY", {"reason": "Your work has been moved to a nearby crew with free capacity so it can start sooner."},
                   dedupe=f"reassign-{p.id}")
    for u in db.scalars(select(User).where(User.crew_id == p.to_crew_id)):
        notify_staff(db, u.id, "WO_ASSIGNED", f"New job {wo.id} reassigned to your crew: {sr.description[:100]}", sr.id, "FIELD")
    db.commit()
    return out(db, p)


@router.post("/reassignments/{pid}/reject")
def reject(pid: int, body: DecideIn | None = None, db: Session = Depends(get_db), actor: Actor = Depends(require_roles(*OFFICERS))):
    p = _get(db, pid, actor)
    p.status, p.decided_by, p.decided_at = "REJECTED", actor.user_id, now()
    from app.models import AgentRun

    if p.agent_run_id and (run := db.get(AgentRun, p.agent_run_id)):
        run.overridden_by, run.override_reason, run.overridden_at = actor.user_id, (body.note if body else None) or "Reassignment rejected", now()
    db.commit()
    return out(db, p)


@router.get("/material-requests")
def material_requests(db: Session = Depends(get_db), actor: Actor = Depends(require_roles(*OFFICERS))):
    return [{"id": m.id, "item": m.item, "qty": m.qty, "sr_id": m.sr_id, "status": m.status, "created_at": m.created_at}
            for m in db.scalars(select(MaterialRequest).order_by(MaterialRequest.id.desc()).limit(50))]


@router.get("/escalations")
def escalations(db: Session = Depends(get_db), actor: Actor = Depends(require_roles(*OFFICERS))):
    from app.models import Escalation

    rows = []
    for e in db.scalars(select(Escalation).order_by(Escalation.id.desc()).limit(100)):
        if not scope.can_access_sr(db, actor, e.sr_id):
            continue
        auth = db.get(User, e.authority_id) if e.authority_id else None
        rows.append({"id": e.id, "sr_id": e.sr_id, "level": e.level, "trigger": e.trigger, "reason_summary": e.reason_summary,
                     "authority": auth.designation if auth else None, "created_at": e.created_at, "deadline": e.deadline,
                     "agent_run_id": e.agent_run_id})
    return rows
