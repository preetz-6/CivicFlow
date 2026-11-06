from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import scope
from app.core.actor import Actor
from app.models import (
    AgentRun, Attachment, Escalation, Feedback, Referral, ServiceRequest, StatusEvent, Timeline, User, WorkOrder,
)
from app.models.enums import Role
from app.modules import geo
from app.modules.complaints.service import dept_name, dept_name_kn, labels, ward_name, ward_name_kn
from app.modules.media.service import attachment_out
from app.modules.sla.service import compute
from app.modules.workflow.table import allowed_targets


def sla_out(sr: ServiceRequest) -> dict:
    v = compute(sr)
    return {"state": v.state, "due_at": v.due_at, "remaining_s": v.remaining_s, "fraction": v.fraction, "label": v.label}


def latest_analysis(db: Session, sr_id: str) -> AgentRun | None:
    return db.scalar(select(AgentRun).where(AgentRun.agent == "investigator", AgentRun.subject_id == sr_id)
                     .order_by(AgentRun.id.desc()).limit(1))


def queue_item(db: Session, sr: ServiceRequest, owners: dict[int, str] | None = None, decisions: dict | None = None) -> dict:
    lat, lon = geo.latlon(sr.location)
    owner_name = (owners or {}).get(sr.owner_id) if owners is not None else (
        db.get(User, sr.owner_id).name if sr.owner_id else None)
    return {
        "id": sr.id, "category": sr.category, "category_label": labels(sr.category)[0], "description": sr.description,
        "status": sr.status, "priority": sr.priority, "ward_id": sr.ward_id, "department_id": sr.department_id,
        "source": sr.source, "reporter_count": sr.reporter_count, "corroboration_count": sr.corroboration_count,
        "escalation_level": sr.escalation_level, "emergency": sr.emergency, "created_at": sr.created_at,
        "sla": sla_out(sr), "owner_name": owner_name,
        "analysis_decision": (decisions or {}).get(sr.id), "lat": lat, "lon": lon,
    }


def wo_out(db: Session, wo: WorkOrder) -> dict:
    photos = db.scalars(select(Attachment).where(Attachment.wo_id == wo.id).order_by(Attachment.id)).all()
    return {
        "id": wo.id, "sr_id": wo.sr_id, "crew_id": wo.crew_id, "status": wo.status, "scope": wo.scope,
        "root_cause": wo.root_cause, "est_cost_inr": wo.est_cost_inr, "asset_id": wo.asset_id,
        "assigned_at": wo.assigned_at, "started_at": wo.started_at, "completed_at": wo.completed_at,
        "verified_at": wo.verified_at, "rework_reason": wo.rework_reason, "rework_count": wo.rework_count,
        "audit_verdict": wo.audit_verdict, "audit_score": wo.audit_score, "audit_run_id": wo.audit_run_id,
        "photos": [attachment_out(p) for p in photos],
    }


def timeline(db: Session, sr_id: str, public_only: bool = True) -> list[dict]:
    q = select(Timeline).where(Timeline.sr_id == sr_id)
    if public_only:
        q = q.where(Timeline.public.is_(True))
    from app.modules.workflow.remarks import stage_kn

    return [{"at": t.at, "stage": t.stage, "stage_kn": stage_kn(t.stage), "remarks": t.remarks, "remarks_kn": t.remarks_kn,
             "actor_type": t.actor_type}
            for t in db.scalars(q.order_by(Timeline.at, Timeline.id))]


def allowed_actions(sr: ServiceRequest, actor: Actor) -> list[str]:
    from app.modules.workflow.table import find_rule

    out = []
    for to in allowed_targets("SR", sr.status):
        rule = find_rule("SR", sr.status, to)
        if actor.role in rule.actors and not (rule.only_if_prev and sr.prev_status != to):
            out.append(to)
    return out


def duplicate_info(db: Session, sr: ServiceRequest, run: AgentRun | None = None) -> dict | None:
    """Why this grievance was merged into another one (or why the agent thinks it may be the same)."""
    if sr.status == "MERGED" and sr.parent_sr_id:
        ev = db.scalar(select(StatusEvent).where(StatusEvent.object_id == sr.id, StatusEvent.to_state == "MERGED")
                       .order_by(StatusEvent.id.desc()).limit(1))
        meta = (ev.meta or {}) if ev else {}
        human = ev is not None and ev.actor_type == "HUMAN"
        return {"merged": True, "parent": sr.parent_sr_id, "confidence": meta.get("confidence"),
                "reason": meta.get("reason") or (ev.reason if ev else None),
                "decided_by": "officer" if human else meta.get("decided_by", "rules"),
                "by": ev.actor_label if ev else None, "at": ev.at if ev else None}
    out = (run.output or {}) if run else {}
    if out.get("duplicate_of") and sr.status == "SUBMITTED":
        return {"merged": False, "parent": out["duplicate_of"], "confidence": out.get("duplicate_confidence"),
                "reason": out.get("duplicate_reason"), "decided_by": None, "by": None, "at": None}
    return None


def detail(db: Session, sr: ServiceRequest, actor: Actor) -> dict:
    d = queue_item(db, sr)
    show_contact = scope.can_see_contact(actor)
    run = latest_analysis(db, sr.id)
    photos = db.scalars(select(Attachment).where(Attachment.sr_id == sr.id).order_by(Attachment.id)).all()
    wos = db.scalars(select(WorkOrder).where(WorkOrder.sr_id == sr.id).order_by(WorkOrder.assigned_at)).all()
    if actor.role == Role.FIELD_TEAM:
        wos = [w for w in wos if w.crew_id == actor.crew_id]
    events = db.scalars(select(StatusEvent).where(StatusEvent.object_id.in_([sr.id] + [w.id for w in wos]))
                        .order_by(StatusEvent.at, StatusEvent.id)).all()
    d.update({
        "address": sr.address, "landmark": sr.landmark, "asset_id": sr.asset_id, "parent_sr_id": sr.parent_sr_id,
        "incident_id": sr.incident_id, "hold_reason": sr.hold_reason, "prev_status": sr.prev_status,
        "contact_name": sr.contact_name if show_contact else None,
        "contact_phone": sr.contact_phone if show_contact else None,
        "tracking_code": sr.tracking_code if show_contact else None,
        "citizen_category": sr.citizen_category,
        "photos": [attachment_out(p) for p in photos],
        "work_orders": [wo_out(db, w) for w in wos],
        "timeline": timeline(db, sr.id, public_only=False),
        "status_events": [{"at": e.at, "object_type": e.object_type, "object_id": e.object_id, "from_state": e.from_state,
                           "to_state": e.to_state, "actor_type": e.actor_type, "actor_label": e.actor_label,
                           "reason": e.reason} for e in events],
        "allowed_actions": allowed_actions(sr, actor),
        "analysis": run_summary(db, run) if run else None,
        "duplicates": list(db.scalars(select(ServiceRequest.id).where(ServiceRequest.parent_sr_id == sr.id))),
        "duplicate_info": duplicate_info(db, sr, run),
        "referrals": [{"id": r.id, "agency": r.agency, "status": r.status, "reason": r.reason, "sent_at": r.sent_at,
                       "followups_sent": r.followups_sent, "agency_status": r.agency_status, "agency_reply": r.agency_reply}
                      for r in db.scalars(select(Referral).where(Referral.sr_id == sr.id))],
        "escalations": [{"level": e.level, "trigger": e.trigger, "reason_summary": e.reason_summary, "created_at": e.created_at}
                        for e in db.scalars(select(Escalation).where(Escalation.sr_id == sr.id).order_by(Escalation.id))],
    })
    return d


def run_summary(db: Session, run: AgentRun) -> dict:
    from app.models import AgentStep

    steps = db.scalars(select(AgentStep).where(AgentStep.run_id == run.id).order_by(AgentStep.idx)).all()
    return {
        "run_id": run.id, "agent": run.agent, "status": run.status, "model": run.model, "confidence": run.confidence,
        "decision": run.decision, "rationale": run.rationale, "output": run.output, "started_at": run.started_at,
        "latency_ms": run.latency_ms, "overridden": run.overridden_by is not None, "override_reason": run.override_reason,
        "accepted": run.accepted_by is not None,
        "steps": [{"idx": s.idx, "tool": s.tool, "args": s.args, "result": s.result_summary, "error": s.error} for s in steps],
    }


def track_view(db: Session, sr: ServiceRequest) -> dict:
    lat, lon = geo.latlon(sr.location)
    en, kn = labels(sr.category)
    photos = db.scalars(select(Attachment).where(
        (Attachment.sr_id == sr.id) | Attachment.wo_id.in_(select(WorkOrder.id).where(WorkOrder.sr_id == sr.id))
    ).order_by(Attachment.id)).all()
    fb = db.scalar(select(Feedback.rating).where(Feedback.sr_id == sr.id, Feedback.rating.is_not(None))
                   .order_by(Feedback.id.desc()).limit(1))
    # after-photos: only the APPROVED attempt of each verified work order (never a photo that failed the audit)
    approved_after: set[int] = set()
    for w in db.scalars(select(WorkOrder).where(WorkOrder.sr_id == sr.id, WorkOrder.status == "VERIFIED")):
        q = select(Attachment.id).where(Attachment.wo_id == w.id, Attachment.kind == "AFTER")
        if w.started_at:
            q = q.where(Attachment.uploaded_at >= w.started_at)
        last = db.scalar(q.order_by(Attachment.id.desc()).limit(1))
        if last:
            approved_after.add(last)
    return {
        "grievance_no": sr.id, "status": sr.status, "category": sr.category, "category_label": en,
        "category_label_kn": kn, "description": sr.description, "submitted_at": sr.created_at,
        "ward_name": ward_name(db, sr.ward_id), "department_name": dept_name(db, sr.department_id),
        "ward_name_kn": ward_name_kn(db, sr.ward_id), "department_name_kn": dept_name_kn(db, sr.department_id),
        "priority": sr.priority, "expected_resolution": compute(sr).due_at or sr.sla_due_at,
        "reporter_count": sr.reporter_count, "escalation_level": sr.escalation_level, "merged_into": sr.parent_sr_id,
        "lat": lat, "lon": lon, "landmark": sr.landmark, "timeline": timeline(db, sr.id),
        "citizen_photos": [attachment_out(p) for p in photos if p.kind == "CITIZEN"],
        "before_photos": [attachment_out(p) for p in photos if p.kind == "BEFORE"],
        # after-photos are shown to citizens only once the work is verified by a human
        "after_photos": [attachment_out(p) for p in photos if p.id in approved_after],
        "can_confirm": sr.status == "RESOLVED", "can_reopen": sr.status == "RESOLVED", "feedback_rating": fb,
    }
