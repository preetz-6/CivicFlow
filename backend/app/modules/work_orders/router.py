from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core import scope
from app.core.actor import Actor
from app.core.clock import now
from app.core.db import get_db
from app.core.errors import DomainError, NotFound
from app.core.security import require_roles
from app.models import Attachment, Crew, ServiceRequest, WorkOrder
from app.models.enums import Role
from app.modules import geo
from app.modules.complaints import serialize
from app.modules.complaints.service import get_sr, labels
from app.modules.media.service import store_photo
from app.modules.workflow.service import next_wo_id, transition
from app.schemas.complaints import WorkOrderOut

router = APIRouter(tags=["work orders"])
OFFICERS = (Role.WARD_OFFICER, Role.CONTROL_ROOM)
OPEN_WO = ("ASSIGNED", "IN_PROGRESS", "REWORK", "ON_HOLD")


def get_wo(db: Session, wo_id: str) -> WorkOrder:
    wo = db.get(WorkOrder, wo_id)
    if wo is None:
        raise NotFound(f"Work order {wo_id} not found")
    return wo


def crew_load(db: Session, crew_id: str) -> int:
    return db.scalar(select(func.count()).select_from(WorkOrder).where(WorkOrder.crew_id == crew_id,
                                                                     WorkOrder.status.in_(OPEN_WO))) or 0


# ------------------------------------------------------------------ officer
@router.get("/crews")
def crews(ward: str | None = None, db: Session = Depends(get_db), actor: Actor = Depends(require_roles(*OFFICERS))):
    q = select(Crew).order_by(Crew.id)
    if ward:
        q = q.where(Crew.ward_id == ward)
    out = []
    for c in db.scalars(q):
        lat, lon = geo.latlon(c.base_location)
        out.append({"id": c.id, "name": c.name, "ward_id": c.ward_id, "skills": c.skills, "capacity": c.capacity,
                    "open_jobs": crew_load(db, c.id), "contractor": c.contractor, "audit_priority": c.audit_priority,
                    "lat": lat, "lon": lon})
    return out


@router.post("/complaints/{sr_id}/work-orders", response_model=WorkOrderOut, status_code=201)
async def create_work_order(
    sr_id: str, crew_id: str = Form(...), scope_text: str = Form(..., alias="scope"),
    root_cause: str | None = Form(None), est_cost_inr: float | None = Form(None), asset_id: str | None = Form(None),
    before_photo: UploadFile | None = File(None),
    db: Session = Depends(get_db), actor: Actor = Depends(require_roles(*OFFICERS)),
):
    """Inspection is merged into work-order creation (brief §6.2): one form, optional before-photo."""
    sr = get_sr(db, sr_id)
    scope.ensure_sr(db, actor, sr.id)
    if sr.status not in ("ASSIGNED", "IN_PROGRESS"):
        raise DomainError(f"Work orders can be created when the grievance is ASSIGNED or IN_PROGRESS (now {sr.status})")
    if db.get(Crew, crew_id) is None:
        raise DomainError(f"Unknown crew {crew_id}")
    from app.domain_config import CATEGORY_MATERIAL

    mat = CATEGORY_MATERIAL.get(sr.category)
    wo = WorkOrder(id=next_wo_id(db), sr_id=sr.id, crew_id=crew_id, asset_id=asset_id or sr.asset_id, scope=scope_text,
                   root_cause=root_cause, est_cost_inr=est_cost_inr, status="ASSIGNED", assigned_at=now(),
                   created_by=actor.user_id, materials={mat[0]: mat[1]} if mat else None)
    db.add(wo)
    db.flush()
    if before_photo and before_photo.filename:
        store_photo(db, await before_photo.read(), before_photo.content_type, kind="BEFORE",
                    uploaded_by=actor.user_id, sr_id=sr.id, wo_id=wo.id)
    from app.core.bus import bus

    bus.publish(db, "work_order.assigned", {"id": wo.id, "sr_id": sr.id, "crew_id": crew_id})
    db.commit()
    return serialize.wo_out(db, wo)


class WoHoldIn(BaseModel):
    reason_code: str


@router.post("/work-orders/{wo_id}/hold")
def wo_hold(wo_id: str, body: WoHoldIn, db: Session = Depends(get_db), actor: Actor = Depends(require_roles(*OFFICERS))):
    wo = get_wo(db, wo_id)
    transition(db, wo, "ON_HOLD", actor, hold_reason=body.reason_code.upper())
    db.commit()
    return {"status": wo.status}


# ------------------------------------------------------------------ field team
def _job(db: Session, wo: WorkOrder) -> dict:
    sr = db.get(ServiceRequest, wo.sr_id)
    lat, lon = geo.latlon(sr.location)
    d = serialize.wo_out(db, wo)
    citizen_photos = db.scalars(select(Attachment).where(Attachment.sr_id == sr.id, Attachment.kind == "CITIZEN")).all()
    from app.modules.media.service import attachment_out

    # NB: no contact_name / contact_phone: field teams never see citizen phone numbers.
    d.update({"category": sr.category, "category_label": labels(sr.category)[0], "description": sr.description,
              "address": sr.address, "landmark": sr.landmark, "lat": lat, "lon": lon, "priority": sr.priority,
              "sr_status": sr.status, "ward_id": sr.ward_id, "citizen_photos": [attachment_out(p) for p in citizen_photos]})
    return d


@router.get("/field/jobs")
def my_jobs(include_done: bool = False, db: Session = Depends(get_db), actor: Actor = Depends(require_roles(Role.FIELD_TEAM))):
    q = scope.scope_wos(select(WorkOrder), actor)
    if not include_done:
        q = q.where(WorkOrder.status.in_(OPEN_WO + ("COMPLETED",)))
    q = q.order_by(WorkOrder.status == "REWORK", WorkOrder.assigned_at.desc())
    return [_job(db, w) for w in db.scalars(q)]


@router.get("/field/jobs/{wo_id}")
def job(wo_id: str, db: Session = Depends(get_db), actor: Actor = Depends(require_roles(Role.FIELD_TEAM))):
    wo = get_wo(db, wo_id)
    scope.ensure_wo(db, actor, wo.id)
    return _job(db, wo)


@router.post("/field/jobs/{wo_id}/start")
def start(wo_id: str, db: Session = Depends(get_db), actor: Actor = Depends(require_roles(Role.FIELD_TEAM))):
    wo = get_wo(db, wo_id)
    transition(db, wo, "IN_PROGRESS", actor)
    db.commit()
    return _job(db, wo)


@router.post("/field/jobs/{wo_id}/photos")
async def upload(wo_id: str, kind: str = Form(...), photo: UploadFile = File(...), db: Session = Depends(get_db),
                 actor: Actor = Depends(require_roles(Role.FIELD_TEAM))):
    wo = get_wo(db, wo_id)
    scope.ensure_wo(db, actor, wo.id)
    kind = kind.upper()
    if kind not in ("BEFORE", "AFTER"):
        raise HTTPException(422, "kind must be BEFORE or AFTER")
    if kind == "AFTER" and wo.status not in ("IN_PROGRESS",):
        raise DomainError("Start the job before uploading the after-photo")
    a = store_photo(db, await photo.read(), photo.content_type, kind=kind, uploaded_by=actor.user_id,
                    sr_id=wo.sr_id, wo_id=wo.id)
    db.commit()
    from app.modules.media.service import attachment_out

    return attachment_out(a)


@router.post("/field/jobs/{wo_id}/complete")
def complete(wo_id: str, db: Session = Depends(get_db), actor: Actor = Depends(require_roles(Role.FIELD_TEAM))):
    """Requires an after-photo uploaded since the job started. Triggers the Evidence Auditor."""
    wo = get_wo(db, wo_id)
    transition(db, wo, "COMPLETED", actor)
    db.commit()
    return _job(db, wo)


@router.post("/field/jobs/{wo_id}/resume")
def field_resume(wo_id: str, db: Session = Depends(get_db), actor: Actor = Depends(require_roles(Role.FIELD_TEAM))):
    wo = get_wo(db, wo_id)
    transition(db, wo, "IN_PROGRESS", actor)
    db.commit()
    return _job(db, wo)


# ------------------------------------------------------------------ control room verification
@router.get("/control/verification")
def verification_queue(db: Session = Depends(get_db), actor: Actor = Depends(require_roles(Role.CONTROL_ROOM))):
    from app.models import AgentRun

    out = []
    for wo in db.scalars(select(WorkOrder).where(WorkOrder.status == "COMPLETED").order_by(WorkOrder.completed_at)):
        d = _job(db, wo)
        run = db.get(AgentRun, wo.audit_run_id) if wo.audit_run_id else None
        d["audit"] = serialize.run_summary(db, run) if run else None
        crew = db.get(Crew, wo.crew_id)
        d["crew_audit_priority"] = crew.audit_priority if crew else None
        out.append(d)
    return out


class RejectWoIn(BaseModel):
    reason: str = Field(min_length=5)


@router.post("/work-orders/{wo_id}/approve")
def approve(wo_id: str, db: Session = Depends(get_db), actor: Actor = Depends(require_roles(Role.CONTROL_ROOM))):
    """Final approval is always human. WO -> VERIFIED; when all WOs are verified the SR follows."""
    wo = get_wo(db, wo_id)
    transition(db, wo, "VERIFIED", actor)
    db.commit()
    sr = db.get(ServiceRequest, wo.sr_id)
    return {"status": wo.status, "sr_status": sr.status}


@router.post("/work-orders/{wo_id}/reject")
def reject(wo_id: str, body: RejectWoIn, db: Session = Depends(get_db), actor: Actor = Depends(require_roles(Role.CONTROL_ROOM))):
    wo = get_wo(db, wo_id)
    transition(db, wo, "REWORK", actor, rework_reason=body.reason)
    from app.models import User
    from app.modules.notifications.service import notify_staff

    for u in db.scalars(select(User).where(User.crew_id == wo.crew_id)):
        notify_staff(db, u.id, "WO_REWORK", f"{wo.id} sent back for rework: {body.reason}", wo.sr_id, "FIELD")
    db.commit()
    return {"status": wo.status}
