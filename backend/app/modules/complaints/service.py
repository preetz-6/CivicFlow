from __future__ import annotations

import secrets
import string
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.actor import Actor
from app.core.bus import bus
from app.core.clock import now
from app.core.errors import DomainError, NotFound
from app.domain_config import (
    CATEGORY_DEPARTMENT, CATEGORY_LABELS, DEFAULT_PRIORITY, EMERGENCY_KEYWORDS, VERIFICATION_HOURS,
)
from app.models import (
    AuditLog, Department, Feedback, ServiceRequest, SlaPolicy, SrReporter, StatusEvent, Timeline, User, Ward,
)
from app.models.enums import Category, Role
from app.modules import geo
from app.modules.media.service import store_photo
from app.modules.notifications.service import notify_citizen
from app.modules.workflow.remarks import SR_REMARKS
from app.modules.workflow.service import next_sr_id, transition


def _tracking_code() -> str:
    return "".join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(8))


def is_emergency(text: str) -> bool:
    t = (text or "").lower()
    return any(k in t for k in EMERGENCY_KEYWORDS)


def ward_officer(db: Session, ward_id: str | None) -> User | None:
    if not ward_id:
        return None
    return db.scalar(select(User).where(User.role == Role.WARD_OFFICER, User.ward_id == ward_id).order_by(User.id))


def apply_sla(db: Session, sr: ServiceRequest, *, restart: bool = False) -> None:
    """Attach the SLA policy for (category, priority). The clock start never moves unless restart=True
    (new complaint). Priority/category changes recompute the due date from the original start."""
    pol = db.scalar(select(SlaPolicy).where(SlaPolicy.category == sr.category, SlaPolicy.priority == sr.priority))
    if pol is None:
        return
    sr.sla_policy_id = pol.id
    if restart or sr.sla_started_at is None:
        sr.sla_started_at = now()
    sr.sla_due_at = sr.sla_started_at + timedelta(hours=pol.resolution_hours)


def create_complaint(
    db: Session, *, category: str, description: str, lat: float, lon: float, address: str | None = None,
    landmark: str | None = None, contact_name: str | None = None, contact_phone: str | None = None,
    anonymous: bool = False, language: str = "en", citizen: User | None = None, source: str = "CITIZEN_WEB",
    photo: tuple[bytes, str] | None = None, actor: Actor | None = None,
) -> ServiceRequest:
    if category not in Category.__members__:
        raise DomainError(f"Unknown category {category}")
    if not geo.in_city(db, lat, lon):
        raise DomainError("The location is outside the CivicFlow Municipal Corporation limits")
    ward = geo.ward_for(db, lat, lon)
    t = now()
    sr = ServiceRequest(
        id=next_sr_id(db), tracking_code=_tracking_code(), category=category, citizen_category=category,
        description=description.strip(), location=geo.make_point(lat, lon), address=address, landmark=landmark,
        ward_id=ward.id if ward else None, department_id=CATEGORY_DEPARTMENT.get(category), status="SUBMITTED",
        priority=DEFAULT_PRIORITY.get(category, "P3"), source=source, citizen_id=citizen.id if citizen else None,
        contact_name=None if anonymous else (contact_name or (citizen.name if citizen else None)),
        contact_phone=None if anonymous else (contact_phone or (citizen.phone if citizen else None)),
        anonymous=anonymous, language=language if language in ("en", "kn") else "en", created_at=t, updated_at=t,
        reporter_count=1,
    )
    if is_emergency(description):
        sr.emergency = True
        sr.priority = "P1"
    owner = ward_officer(db, sr.ward_id)
    sr.owner_id = owner.id if owner else None  # every open complaint has exactly one owner
    apply_sla(db, sr, restart=True)
    db.add(sr)
    db.flush()
    db.add(SrReporter(sr_id=sr.id, citizen_user_id=citizen.id if citizen else None,
                      contact_name=sr.contact_name, contact_phone=sr.contact_phone, language=sr.language, added_at=t))
    if photo:
        store_photo(db, photo[0], photo[1], kind="CITIZEN", uploaded_by=citizen.id if citizen else None, sr_id=sr.id)
    a = actor or (Actor.from_user(citizen) if citizen else Actor.system("intake"))
    db.add(StatusEvent(object_type="SR", object_id=sr.id, from_state=None, to_state="SUBMITTED",
                       actor_type=str(a.kind), actor=a.id, actor_label=a.label, at=t,
                       meta={"source": source, "emergency": sr.emergency}))
    db.add(AuditLog(actor=a.id, action="SR.create", object=f"SR:{sr.id}", before_json=None,
                    after_json={"category": category, "ward_id": sr.ward_id, "priority": sr.priority, "source": source}, at=t))
    stage, en, kn = SR_REMARKS["SUBMITTED"]
    if source == "VEHICLE_FEED":
        en = "Registered automatically from connected-vehicle road data."
        kn = "ಸಂಪರ್ಕಿತ ವಾಹನಗಳ ರಸ್ತೆ ಮಾಹಿತಿಯಿಂದ ಸ್ವಯಂಚಾಲಿತವಾಗಿ ನೋಂದಾಯಿಸಲಾಗಿದೆ."
    db.add(Timeline(sr_id=sr.id, stage=stage, remarks=en, remarks_kn=kn, actor_type=str(a.kind), at=t))
    bus.publish(db, "complaint.submitted", {"id": sr.id, "source": source, "emergency": sr.emergency})
    if sr.emergency:
        bus.publish(db, "control_room.alert", {"sr_id": sr.id, "reason": "Emergency keywords in description"})
    return sr


def get_sr(db: Session, sr_id: str) -> ServiceRequest:
    sr = db.get(ServiceRequest, sr_id)
    if sr is None:
        raise NotFound(f"Grievance {sr_id} not found")
    return sr


def find_by_tracking(db: Session, grievance_no: str, code: str) -> ServiceRequest:
    """Citizen access without login: grievance number + (tracking code OR registered mobile)."""
    sr = db.get(ServiceRequest, grievance_no.strip().upper())
    code = (code or "").strip()
    if sr is None or not code:
        raise NotFound("No grievance matches that number and code")
    ok = code.upper() == sr.tracking_code or (sr.contact_phone and code[-10:] == sr.contact_phone[-10:])
    if not ok:
        rep = db.scalar(select(SrReporter).where(SrReporter.sr_id == sr.id, SrReporter.contact_phone == code))
        ok = rep is not None
    if not ok:
        raise NotFound("No grievance matches that number and code")
    return sr


def labels(category: str) -> tuple[str, str]:
    return CATEGORY_LABELS.get(category, (category, category))


def ward_name(db: Session, ward_id: str | None) -> str | None:
    w = db.get(Ward, ward_id) if ward_id else None
    return f"{w.id} {w.name}" if w else None


def dept_name(db: Session, dept_id: str | None) -> str | None:
    d = db.get(Department, dept_id) if dept_id else None
    return d.name if d else None


def resolve_after_verification(db: Session, sr: ServiceRequest) -> None:
    """VERIFIED -> RESOLVED (System) after telling every reporter, with before/after photos on Track."""
    notify_citizen(db, sr, "RESOLVED")
    sr.verification_due_at = now() + timedelta(hours=VERIFICATION_HOURS.get(sr.priority, 168))
    transition(db, sr, "RESOLVED", Actor.system("workflow"))


def citizen_confirm(db: Session, sr: ServiceRequest, actor: Actor, rating: int | None, comment: str | None,
                    scope_verified: bool) -> None:
    transition(db, sr, "CLOSED", actor, closure_type="CITIZEN", scope_verified=scope_verified)
    db.add(Feedback(sr_id=sr.id, rating=rating, comment=comment, created_at=now()))
    notify_citizen(db, sr, "CLOSED")


def citizen_reopen(db: Session, sr: ServiceRequest, actor: Actor, reason: str, scope_verified: bool) -> None:
    transition(db, sr, "REOPENED", actor, reopen_reason=reason, scope_verified=scope_verified)
    db.add(Feedback(sr_id=sr.id, reopen_reason=reason, created_at=now()))
    notify_citizen(db, sr, "REOPENED", dedupe=str(sr.reopen_count))
