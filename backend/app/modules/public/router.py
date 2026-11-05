"""Public (no-login) endpoints: stats strip, ticker, ward list, categories, agency inbox (simulated)."""
from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Depends
from geoalchemy2.shape import to_shape
from pydantic import BaseModel
from shapely.geometry import mapping
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.actor import Actor
from app.core.clock import now
from app.core.db import get_db
from app.core.errors import NotFound
from app.core.security import require_roles
from app.domain_config import CATEGORY_LABELS
from app.models import AgencyMessage, Department, Incident, Notification, Referral, ServiceRequest, User, Ward
from app.models.enums import Role

router = APIRouter(tags=["public"])

STATIC_NOTICES = [
    {"id": "notice-1", "text": "Lodge grievances online 24x7; track with your Grievance No. and mobile number.",
     "text_kn": "ದೂರುಗಳನ್ನು 24x7 ಆನ್‌ಲೈನ್‌ನಲ್ಲಿ ಸಲ್ಲಿಸಿ; ದೂರು ಸಂಖ್ಯೆ ಮತ್ತು ಮೊಬೈಲ್ ಸಂಖ್ಯೆಯೊಂದಿಗೆ ಸ್ಥಿತಿ ತಿಳಿಯಿರಿ.", "new": False},
    {"id": "notice-2", "text": "Citizen Charter: potholes on arterial roads are attended within 5 days.",
     "text_kn": "ನಾಗರಿಕ ಸನ್ನದು: ಮುಖ್ಯ ರಸ್ತೆಗಳ ಗುಂಡಿಗಳನ್ನು 5 ದಿನಗಳಲ್ಲಿ ಸರಿಪಡಿಸಲಾಗುತ್ತದೆ.", "new": False},
]


@router.get("/public/stats")
def stats(db: Session = Depends(get_db)):
    total = db.scalar(select(func.count()).select_from(ServiceRequest)) or 0
    unique = db.scalar(select(func.count()).select_from(ServiceRequest).where(ServiceRequest.status != "MERGED")) or 0
    closed = db.scalars(select(ServiceRequest).where(ServiceRequest.status == "CLOSED")).all()
    within = [s for s in closed if s.resolved_at and s.sla_due_at and
              s.resolved_at <= s.sla_due_at + (s.sla_paused_total or timedelta(0))]
    days = [(s.resolved_at - s.created_at).total_seconds() / 86400 for s in closed if s.resolved_at]
    return {
        "total": total, "unique_issues": unique, "resolved": len(closed),
        "resolved_citizen_confirmed": sum(s.closure_type == "CITIZEN" for s in closed),
        "resolved_auto_closed": sum(s.closure_type == "AUTO" for s in closed),
        "within_sla_pct": round(100 * len(within) / len(closed), 1) if closed else None,
        "avg_days": round(sum(days) / len(days), 1) if days else None,
        "reopen_rate_pct": round(100 * sum(s.reopen_count > 0 for s in closed) / len(closed), 1) if closed else None,
        "visits": _visits(db),
        "as_of": now(),
    }


def _visits(db) -> int:
    from app.models import SystemState

    row = db.get(SystemState, "visits")
    return int(row.value.get("count", 0)) if row else 12873


@router.get("/public/ticker")
def ticker(db: Session = Depends(get_db)):
    """Newest first: published Surge Commander advisories, then standing notices."""
    items = [{"id": f"incident-{i.id}", "text": i.advisory_draft, "text_kn": i.advisory_draft_kn, "new": True,
              "published_at": i.published_at}
             for i in db.scalars(select(Incident).where(Incident.advisory_published.is_(True))
                                 .order_by(Incident.published_at.desc()))]
    seeded_at = now() - timedelta(days=10)
    return items + [{**n, "published_at": seeded_at} for n in STATIC_NOTICES]


@router.post("/public/visit")
def visit(db: Session = Depends(get_db)):
    """Called once per browser session by the web app (footer 'Visitors: N'). Atomic upsert: concurrent calls are safe."""
    from sqlalchemy import text

    n = db.execute(text("""
        INSERT INTO system_state (key, value) VALUES ('visits', '{"count": 12874}'::jsonb)
        ON CONFLICT (key) DO UPDATE
          SET value = jsonb_build_object('count', COALESCE((system_state.value->>'count')::int, 12873) + 1)
        RETURNING (value->>'count')::int""")).scalar_one()
    db.commit()
    return {"visits": n}


@router.get("/public/sla-policies")
def sla_policies(db: Session = Depends(get_db)):
    from app.models import SlaPolicy

    return [{"category": p.category, "category_label": CATEGORY_LABELS.get(p.category, (p.category,))[0],
             "priority": p.priority, "resolution_hours": p.resolution_hours, "verification_hours": p.verification_hours}
            for p in db.scalars(select(SlaPolicy).order_by(SlaPolicy.category, SlaPolicy.priority))]


@router.get("/public/categories")
def categories():
    return [{"id": k, "label": v[0], "label_kn": v[1]} for k, v in CATEGORY_LABELS.items()]


@router.get("/public/wards")
def wards(geometry: bool = False, db: Session = Depends(get_db)):
    out = []
    for w in db.scalars(select(Ward).order_by(Ward.id)):
        officer = db.scalar(select(User).where(User.role == Role.WARD_OFFICER, User.ward_id == w.id))
        d = {"id": w.id, "name": w.name, "name_kn": w.name_kn, "zone": w.zone,
             "officer": {"name": officer.name, "designation": officer.designation, "phone": "1800-000-0000 (Demo)"} if officer else None}
        if geometry:
            d["geometry"] = mapping(to_shape(w.geom))
        out.append(d)
    return out


@router.get("/public/departments")
def departments(db: Session = Depends(get_db)):
    return [{"id": d.id, "name": d.name, "name_kn": d.name_kn} for d in db.scalars(select(Department))]


# ------------------------------------------------------------------ notifications outbox (staff view)
@router.get("/notifications")
def outbox(sr_id: str | None = None, recipient_type: str | None = None, limit: int = 100, db: Session = Depends(get_db),
           actor: Actor = Depends(require_roles(Role.WARD_OFFICER, Role.CONTROL_ROOM))):
    q = select(Notification).order_by(Notification.id.desc()).limit(min(limit, 500))
    if sr_id:
        q = q.where(Notification.related_sr_id == sr_id)
    if recipient_type:
        q = q.where(Notification.recipient_type == recipient_type)
    return [{"id": n.id, "at": n.created_at, "recipient": n.recipient if n.recipient.startswith(("user:", "agency:")) else f"******{n.recipient[-4:]}",
             "recipient_type": n.recipient_type, "channel": n.channel, "language": n.language, "event": n.event,
             "body": n.body, "sr_id": n.related_sr_id, "simulated": True} for n in db.scalars(q)]


# ------------------------------------------------------------------ External Agency Inbox (SIMULATED)
@router.get("/agency/inbox")
def agency_inbox(agency: str | None = None, db: Session = Depends(get_db),
                 actor: Actor = Depends(require_roles(Role.WARD_OFFICER, Role.CONTROL_ROOM))):
    q = select(Referral).where(Referral.status != "DRAFT").order_by(Referral.sent_at.desc())
    if agency:
        q = q.where(Referral.agency == agency)
    out = []
    for r in db.scalars(q):
        sr = db.get(ServiceRequest, r.sr_id)
        msgs = db.scalars(select(AgencyMessage).where(AgencyMessage.referral_id == r.id).order_by(AgencyMessage.id)).all()
        out.append({"id": r.id, "agency": r.agency, "sr_id": r.sr_id, "category": sr.category, "description": sr.description,
                    "reason": r.reason, "status": r.status, "sent_at": r.sent_at, "followups_sent": r.followups_sent,
                    "agency_status": r.agency_status, "agency_reply": r.agency_reply, "simulated": True,
                    "messages": [{"direction": m.direction, "body": m.body, "at": m.at} for m in msgs]})
    return out


class AgencyReplyIn(BaseModel):
    status: str  # ACKNOWLEDGED | IN_PROGRESS | RESOLVED
    message: str


@router.post("/agency/referrals/{ref_id}/reply")
def agency_reply(ref_id: int, body: AgencyReplyIn, db: Session = Depends(get_db),
                 actor: Actor = Depends(require_roles(Role.WARD_OFFICER, Role.CONTROL_ROOM))):
    from app.modules.referrals.service import agency_reply as do_reply

    r = db.get(Referral, ref_id)
    if r is None:
        raise NotFound("Referral not found")
    do_reply(db, r, body.status.upper(), body.message)
    db.commit()
    return {"ok": True, "agency_status": r.agency_status}
