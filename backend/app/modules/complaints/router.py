from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core import scope
from app.core.actor import Actor
from app.core.clock import now
from app.core.db import get_db
from app.core.errors import DomainError
from app.core.security import current_actor, current_user_optional, require_roles
from app.models import AgentRun, AuditLog, ServiceRequest, User
from app.models.enums import ActorKind, Role
from app.modules.complaints import serialize
from app.modules.complaints.service import (
    apply_sla, citizen_confirm, citizen_reopen, create_complaint, dept_name, find_by_tracking, get_sr, labels,
    ward_name,
)
from app.modules.notifications.service import notify_citizen
from app.modules.sla.service import compute
from app.modules.workflow.service import transition
from app.schemas.common import Page
from app.schemas.complaints import (
    AcceptIn, AckSlip, ComplaintDetail, ConfirmIn, HoldIn, OverrideIn, QueueItem, ReasonIn, RejectIn, ReopenIn,
    TrackView,
)

router = APIRouter(tags=["complaints"])
OFFICERS = (Role.WARD_OFFICER, Role.CONTROL_ROOM)


def ack_slip(db: Session, sr: ServiceRequest) -> dict:
    en, kn = labels(sr.category)
    return {
        "grievance_no": sr.id, "tracking_code": sr.tracking_code, "submitted_at": sr.created_at,
        "category": sr.category, "category_label": en, "category_label_kn": kn, "ward_id": sr.ward_id,
        "ward_name": ward_name(db, sr.ward_id), "department_id": sr.department_id,
        "department_name": dept_name(db, sr.department_id), "expected_resolution": sr.sla_due_at, "status": sr.status,
    }


# ------------------------------------------------------------------ citizen
@router.post("/complaints", response_model=AckSlip, status_code=201)
async def lodge(
    category: str = Form(...), description: str = Form(..., min_length=10), lat: float = Form(...),
    lon: float = Form(...), address: str | None = Form(None), landmark: str | None = Form(None),
    contact_name: str | None = Form(None), contact_phone: str | None = Form(None), anonymous: bool = Form(False),
    language: str = Form("en"), photo: UploadFile | None = File(None),
    db: Session = Depends(get_db), user: User | None = Depends(current_user_optional),
):
    if user is not None and user.role != Role.CITIZEN:
        user = None  # staff filing on behalf (helpdesk) are not the citizen
    if not anonymous and not (contact_phone or (user and user.phone)):
        raise HTTPException(422, "Mobile number is required unless filing anonymously")
    data = (await photo.read(), photo.content_type) if photo and photo.filename else None
    sr = create_complaint(
        db, category=category, description=description, lat=lat, lon=lon, address=address, landmark=landmark,
        contact_name=contact_name, contact_phone=contact_phone, anonymous=anonymous, language=language,
        citizen=user, photo=data,
    )
    db.commit()
    return ack_slip(db, sr)


@router.get("/complaints/{sr_id}/ack", response_model=AckSlip)
def get_ack(sr_id: str, code: str, db: Session = Depends(get_db)):
    return ack_slip(db, find_by_tracking(db, sr_id, code))


@router.get("/complaints/track", response_model=TrackView)
def track(no: str, code: str, db: Session = Depends(get_db)):
    sr = find_by_tracking(db, no, code)
    if sr.status == "MERGED" and sr.parent_sr_id:
        view = serialize.track_view(db, db.get(ServiceRequest, sr.parent_sr_id))
        view["grievance_no"], view["merged_into"] = sr.id, sr.parent_sr_id
        return view
    return serialize.track_view(db, sr)


@router.get("/my/complaints", response_model=list[QueueItem])
def my_complaints(db: Session = Depends(get_db), actor: Actor = Depends(require_roles(Role.CITIZEN))):
    q = scope.scope_srs(select(ServiceRequest), actor).order_by(ServiceRequest.created_at.desc()).limit(50)
    return [serialize.queue_item(db, sr) for sr in db.scalars(q)]


def _citizen_actor(db: Session, sr: ServiceRequest, code: str | None, user: User | None) -> tuple[Actor, bool]:
    if user is not None and user.role == Role.CITIZEN and scope.can_access_sr(db, Actor.from_user(user), sr.id):
        return Actor.from_user(user), False
    if code:
        find_by_tracking(db, sr.id, code)
        return Actor(kind=ActorKind.HUMAN, id=f"citizen:{sr.tracking_code}", label="Citizen (tracking code)",
                     role=Role.CITIZEN), True
    raise HTTPException(403, "Log in or provide the tracking code")


@router.post("/complaints/{sr_id}/confirm")
def confirm(sr_id: str, body: ConfirmIn, db: Session = Depends(get_db), user: User | None = Depends(current_user_optional)):
    sr = get_sr(db, sr_id)
    actor, verified = _citizen_actor(db, sr, body.code, user)
    citizen_confirm(db, sr, actor, body.rating, body.comment, verified)
    db.commit()
    return {"status": sr.status}


@router.post("/complaints/{sr_id}/reopen")
def reopen(sr_id: str, body: ReopenIn, db: Session = Depends(get_db), user: User | None = Depends(current_user_optional)):
    sr = get_sr(db, sr_id)
    actor, verified = _citizen_actor(db, sr, body.code, user)
    citizen_reopen(db, sr, actor, body.reason, verified)
    db.commit()
    return {"status": sr.status}


# ------------------------------------------------------------------ officer
@router.get("/officer/queue", response_model=Page[QueueItem])
def queue(
    status: str | None = None, priority: str | None = None, category: str | None = None, ward: str | None = None,
    sla: str | None = Query(None, description="ON_TRACK|AT_RISK|BREACHED|PAUSED"), q: str | None = None,
    open_only: bool = True, page: int = 1, page_size: int = Query(10, le=100),
    db: Session = Depends(get_db), actor: Actor = Depends(require_roles(*OFFICERS)),
):
    stmt = scope.scope_srs(select(ServiceRequest), actor)
    if status:
        stmt = stmt.where(ServiceRequest.status.in_(status.split(",")))
    elif open_only:
        stmt = stmt.where(ServiceRequest.status.notin_(["CLOSED", "REJECTED", "MERGED"]))
    if priority:
        stmt = stmt.where(ServiceRequest.priority.in_(priority.split(",")))
    if category:
        stmt = stmt.where(ServiceRequest.category.in_(category.split(",")))
    if ward:
        stmt = stmt.where(ServiceRequest.ward_id == ward)
    if q:
        stmt = stmt.where(or_(ServiceRequest.id.ilike(f"%{q}%"), ServiceRequest.description.ilike(f"%{q}%")))
    rows = db.scalars(stmt.order_by(ServiceRequest.emergency.desc(), ServiceRequest.priority, ServiceRequest.created_at)).all()
    if sla:
        rows = [r for r in rows if compute(r).state == sla]
    total = len(rows)
    rows = rows[(page - 1) * page_size: page * page_size]
    owners = dict(db.execute(select(User.id, User.name).where(User.id.in_({r.owner_id for r in rows if r.owner_id}))).all())
    decisions = dict(db.execute(
        select(AgentRun.subject_id, AgentRun.decision).where(AgentRun.agent == "investigator",
                                                             AgentRun.subject_id.in_([r.id for r in rows]))
        .order_by(AgentRun.id)
    ).all())
    return {"items": [serialize.queue_item(db, r, owners, decisions) for r in rows], "total": total, "page": page,
            "page_size": page_size}


@router.get("/complaints/{sr_id}", response_model=ComplaintDetail)
def complaint_detail(sr_id: str, db: Session = Depends(get_db), actor: Actor = Depends(current_actor)):
    sr = get_sr(db, sr_id)
    scope.ensure_sr(db, actor, sr.id)
    return serialize.detail(db, sr, actor)


def _officer_sr(db, sr_id, actor) -> ServiceRequest:
    sr = get_sr(db, sr_id)
    scope.ensure_sr(db, actor, sr.id)
    return sr


def _mark_run(db: Session, sr_id: str, actor: Actor, *, overridden: str | None = None) -> None:
    from app.modules.complaints.serialize import latest_analysis

    run = latest_analysis(db, sr_id)
    if run is None:
        return
    if overridden:
        run.overridden_by, run.override_reason, run.overridden_at = actor.user_id, overridden, now()
    else:
        run.accepted_by = actor.user_id


def _send_referral(db: Session, sr: ServiceRequest) -> None:
    from app.models import Referral

    for r in db.scalars(select(Referral).where(Referral.sr_id == sr.id, Referral.status == "DRAFT")):
        from app.modules.referrals.service import send_referral

        send_referral(db, r)


@router.post("/complaints/{sr_id}/accept")
def accept(sr_id: str, body: AcceptIn, db: Session = Depends(get_db), actor: Actor = Depends(require_roles(*OFFICERS))):
    """Accept the System Analysis brief as-is -> ASSIGNED."""
    sr = _officer_sr(db, sr_id, actor)
    owner = body.owner_id or sr.owner_id or actor.user_id
    to = "ASSIGNED"
    transition(db, sr, to, actor, owner_id=owner, department_id=body.department_id or sr.department_id,
               reason=body.note or "Accepted System Analysis")
    _mark_run(db, sr.id, actor)
    _send_referral(db, sr)
    notify_citizen(db, sr, "ASSIGNED", dedupe=str(sr.reopen_count))
    db.commit()
    return {"status": sr.status}


@router.post("/complaints/{sr_id}/override")
def override(sr_id: str, body: OverrideIn, db: Session = Depends(get_db), actor: Actor = Depends(require_roles(*OFFICERS))):
    """Officer disagrees with the System Analysis: change fields (reason required), then assign or merge."""
    sr = _officer_sr(db, sr_id, actor)
    before = {"category": sr.category, "priority": sr.priority, "department_id": sr.department_id, "owner_id": sr.owner_id}
    if body.category:
        sr.category = body.category
    if body.priority:
        sr.priority = body.priority
    if body.department_id:
        sr.department_id = body.department_id
    if body.category or body.priority:
        apply_sla(db, sr)  # due date recomputed from the ORIGINAL start; clock never resets
    db.add(AuditLog(actor=actor.id, action="SR.override", object=f"SR:{sr.id}", before_json=before,
                    after_json={"category": sr.category, "priority": sr.priority, "department_id": sr.department_id,
                                "reason": body.reason}, at=now()))
    _mark_run(db, sr.id, actor, overridden=body.reason)
    if body.merge_into:
        _merge(db, sr, body.merge_into, actor)
    else:
        transition(db, sr, "ASSIGNED", actor, owner_id=body.owner_id or sr.owner_id or actor.user_id,
                   department_id=sr.department_id, reason=f"Override: {body.reason}")
        _send_referral(db, sr)
        notify_citizen(db, sr, "ASSIGNED", dedupe=str(sr.reopen_count))
    db.commit()
    return {"status": sr.status}


def _merge(db: Session, sr: ServiceRequest, parent_id: str, actor: Actor) -> None:
    from app.modules.complaints.merge import merge_into

    merge_into(db, sr, get_sr(db, parent_id), actor)


@router.post("/complaints/{sr_id}/hold")
def hold(sr_id: str, body: HoldIn, db: Session = Depends(get_db), actor: Actor = Depends(require_roles(*OFFICERS))):
    sr = _officer_sr(db, sr_id, actor)
    transition(db, sr, "ON_HOLD", actor, hold_reason=body.reason_code.upper(), reason=body.note)
    db.commit()
    return {"status": sr.status, "sla": serialize.sla_out(sr)}


@router.post("/complaints/{sr_id}/resume")
def resume(sr_id: str, db: Session = Depends(get_db), actor: Actor = Depends(require_roles(*OFFICERS))):
    sr = _officer_sr(db, sr_id, actor)
    if not sr.prev_status:
        raise DomainError("Not on hold")
    transition(db, sr, sr.prev_status, actor)
    db.commit()
    return {"status": sr.status, "sla": serialize.sla_out(sr)}


@router.post("/complaints/{sr_id}/reject")
def reject(sr_id: str, body: RejectIn, db: Session = Depends(get_db), actor: Actor = Depends(require_roles(*OFFICERS))):
    sr = _officer_sr(db, sr_id, actor)
    transition(db, sr, "REJECTED", actor, rejection_reason_code=body.reason_code,
               rejection_explanation=body.explanation, reason=body.explanation)
    _mark_run(db, sr.id, actor, overridden=f"Rejected: {body.explanation}")
    notify_citizen(db, sr, "REJECTED", {"reason": body.explanation})
    db.commit()
    return {"status": sr.status}


@router.post("/complaints/{sr_id}/merge/{parent_id}")
def merge(sr_id: str, parent_id: str, db: Session = Depends(get_db), actor: Actor = Depends(require_roles(*OFFICERS))):
    sr = _officer_sr(db, sr_id, actor)
    _merge(db, sr, parent_id, actor)
    db.commit()
    return {"status": sr.status}


@router.post("/complaints/{sr_id}/unmerge")
def unmerge(sr_id: str, body: ReasonIn, db: Session = Depends(get_db), actor: Actor = Depends(require_roles(*OFFICERS))):
    from app.modules.complaints.merge import unmerge as do_unmerge

    sr = _officer_sr(db, sr_id, actor)
    do_unmerge(db, sr, actor, body.reason)
    db.commit()
    return {"status": sr.status}


@router.post("/complaints/{sr_id}/reassign-owner/{user_id}")
def reassign_owner(sr_id: str, user_id: int, body: ReasonIn, db: Session = Depends(get_db),
                   actor: Actor = Depends(require_roles(*OFFICERS))):
    sr = _officer_sr(db, sr_id, actor)
    u = db.get(User, user_id)
    if u is None or u.role not in (Role.WARD_OFFICER, Role.CONTROL_ROOM):
        raise DomainError("Owner must be an officer")
    db.add(AuditLog(actor=actor.id, action="SR.owner_change", object=f"SR:{sr.id}", before_json={"owner_id": sr.owner_id},
                    after_json={"owner_id": user_id, "reason": body.reason}, at=now()))
    sr.owner_id = user_id
    db.commit()
    return {"owner_id": sr.owner_id}


@router.get("/officer/stats")
def officer_stats(db: Session = Depends(get_db), actor: Actor = Depends(require_roles(*OFFICERS))):
    base = scope.scope_srs(select(ServiceRequest), actor).where(ServiceRequest.status.notin_(["CLOSED", "REJECTED", "MERGED"]))
    rows = db.scalars(base).all()
    states = [compute(r).state for r in rows]
    return {
        "open": len(rows), "submitted": sum(r.status == "SUBMITTED" for r in rows),
        "at_risk": states.count("AT_RISK"), "breached": states.count("BREACHED"),
        "escalated": sum(r.escalation_level > 0 for r in rows), "p1": sum(r.priority == "P1" for r in rows),
        "awaiting_verification": db.scalar(select(func.count()).select_from(base.where(ServiceRequest.status == "WORK_COMPLETED").subquery())),
    }
