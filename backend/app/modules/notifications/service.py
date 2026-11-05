"""Notification outbox (simulated SMS). Template-first; agents may pass polished wording.

notify_citizen() writes one row per reporter (the original one and everyone merged in),
in each reporter's own language, and is idempotent per (sr, event, dedupe).
"""
from __future__ import annotations

import hashlib

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.clock import now
from app.domain_config import CATEGORY_LABELS
from app.models import Notification, ServiceRequest, SrReporter, User

TEMPLATES: dict[str, tuple[str, str]] = {
    "ACK": (
        "CivicFlow: Grievance {sr_id} ({category}) registered. Expected resolution by {due}. Track with code {code}.",
        "ಸಿವಿಕ್‌ಫ್ಲೋ: ದೂರು {sr_id} ({category_kn}) ನೋಂದಾಯಿಸಲಾಗಿದೆ. {due} ರೊಳಗೆ ಪರಿಹಾರ ನಿರೀಕ್ಷಿಸಲಾಗಿದೆ. ಟ್ರ್ಯಾಕ್ ಕೋಡ್ {code}.",
    ),
    "MERGED": (
        "CivicFlow: Your grievance {sr_id} has been linked with {parent} for the same issue ({count} citizens reported it). You will keep receiving updates.",
        "ಸಿವಿಕ್‌ಫ್ಲೋ: ನಿಮ್ಮ ದೂರು {sr_id} ಅನ್ನು ಅದೇ ಸಮಸ್ಯೆಯ {parent} ಜೊತೆ ಜೋಡಿಸಲಾಗಿದೆ ({count} ನಾಗರಿಕರು ವರದಿ ಮಾಡಿದ್ದಾರೆ). ನಿಮಗೆ ಮಾಹಿತಿ ಮುಂದುವರಿಯುತ್ತದೆ.",
    ),
    "ASSIGNED": (
        "CivicFlow: Grievance {sr_id} is assigned to {officer}. Expected resolution by {due}.",
        "ಸಿವಿಕ್‌ಫ್ಲೋ: ದೂರು {sr_id} ಅನ್ನು {officer} ಅವರಿಗೆ ವಹಿಸಲಾಗಿದೆ. {due} ರೊಳಗೆ ಪರಿಹಾರ ನಿರೀಕ್ಷಿಸಲಾಗಿದೆ.",
    ),
    "IN_PROGRESS": (
        "CivicFlow: Work has started on grievance {sr_id}.",
        "ಸಿವಿಕ್‌ಫ್ಲೋ: ದೂರು {sr_id} ಕುರಿತು ಕೆಲಸ ಪ್ರಾರಂಭವಾಗಿದೆ.",
    ),
    "REFERRED": (
        "CivicFlow: Grievance {sr_id} needs action by {agency}. We have referred it to them and will follow up.",
        "ಸಿವಿಕ್‌ಫ್ಲೋ: ದೂರು {sr_id} ಗೆ {agency} ಕ್ರಮ ಅಗತ್ಯ. ನಾವು ಅವರಿಗೆ ಕಳುಹಿಸಿದ್ದೇವೆ ಮತ್ತು ಅನುಸರಿಸುತ್ತೇವೆ.",
    ),
    "DELAY": (
        "CivicFlow: Update on {sr_id}: {reason}",
        "ಸಿವಿಕ್‌ಫ್ಲೋ: {sr_id} ಕುರಿತು ಮಾಹಿತಿ: {reason_kn}",
    ),
    "INCIDENT": (
        "CivicFlow: Your grievance {sr_id} is part of an active incident ({incident}) being handled by our crews.",
        "ಸಿವಿಕ್‌ಫ್ಲೋ: ನಿಮ್ಮ ದೂರು {sr_id} ಸಕ್ರಿಯ ಘಟನೆಯ ({incident}) ಭಾಗವಾಗಿದ್ದು, ನಮ್ಮ ತಂಡಗಳು ಕಾರ್ಯನಿರ್ವಹಿಸುತ್ತಿವೆ.",
    ),
    "RESOLVED": (
        "CivicFlow: Grievance {sr_id} is resolved. Before/after photos: track with code {code}. Please confirm or reopen within {window}.",
        "ಸಿವಿಕ್‌ಫ್ಲೋ: ದೂರು {sr_id} ಪರಿಹರಿಸಲಾಗಿದೆ. ಮೊದಲು/ನಂತರದ ಫೋಟೋಗಳನ್ನು ಕೋಡ್ {code} ಮೂಲಕ ನೋಡಿ. {window} ಒಳಗೆ ದೃಢೀಕರಿಸಿ ಅಥವಾ ಮರುತೆರೆಯಿರಿ.",
    ),
    "CLOSED": (
        "CivicFlow: Grievance {sr_id} is closed. Thank you for helping improve your ward.",
        "ಸಿವಿಕ್‌ಫ್ಲೋ: ದೂರು {sr_id} ಮುಕ್ತಾಯಗೊಂಡಿದೆ. ನಿಮ್ಮ ವಾರ್ಡ್ ಸುಧಾರಣೆಗೆ ಸಹಕರಿಸಿದ್ದಕ್ಕೆ ಧನ್ಯವಾದಗಳು.",
    ),
    "REJECTED": (
        "CivicFlow: Grievance {sr_id} could not be accepted. Reason: {reason}",
        "ಸಿವಿಕ್‌ಫ್ಲೋ: ದೂರು {sr_id} ಸ್ವೀಕರಿಸಲಾಗಲಿಲ್ಲ. ಕಾರಣ: {reason_kn}",
    ),
    "REOPENED": (
        "CivicFlow: Grievance {sr_id} has been reopened and will be investigated again.",
        "ಸಿವಿಕ್‌ಫ್ಲೋ: ದೂರು {sr_id} ಮರುತೆರೆಯಲಾಗಿದೆ ಮತ್ತು ಮತ್ತೆ ಪರಿಶೀಲಿಸಲಾಗುವುದು.",
    ),
    "CORROBORATED": (
        "CivicFlow: Your report {sr_id} has been confirmed by {vehicles} connected vehicles. Priority has been raised.",
        "ಸಿವಿಕ್‌ಫ್ಲೋ: ನಿಮ್ಮ ದೂರು {sr_id} ಅನ್ನು {vehicles} ಸಂಪರ್ಕಿತ ವಾಹನಗಳು ದೃಢಪಡಿಸಿವೆ. ಆದ್ಯತೆ ಹೆಚ್ಚಿಸಲಾಗಿದೆ.",
    ),
}


class _Safe(dict):
    def __missing__(self, k):
        return ""


def _context(db: Session, sr: ServiceRequest, extra: dict) -> dict:
    owner = db.get(User, sr.owner_id) if sr.owner_id else None
    en, kn = CATEGORY_LABELS.get(sr.category, (sr.category, sr.category))
    ctx = {
        "sr_id": sr.id, "category": en, "category_kn": kn, "code": sr.tracking_code,
        "due": sr.sla_due_at.strftime("%d %b %Y") if sr.sla_due_at else "-",
        "officer": owner.designation if owner and owner.designation else "the ward officer",
        "count": sr.reporter_count, "window": "7 days" if sr.priority != "P1" else "24 hours",
    }
    ctx.update({k: v for k, v in (extra or {}).items() if v is not None})
    ctx.setdefault("reason_kn", ctx.get("reason", ""))
    return ctx


def recipients(db: Session, sr: ServiceRequest) -> list[tuple[str, str]]:
    """(recipient, language) for every reporter of this SR, deduplicated."""
    out: dict[str, str] = {}
    for r in db.scalars(select(SrReporter).where(SrReporter.sr_id == sr.id)):
        key = f"user:{r.citizen_user_id}" if r.citizen_user_id else (r.contact_phone or "")
        if key:
            out.setdefault(key, r.language or "en")
    if not out:
        key = f"user:{sr.citizen_id}" if sr.citizen_id else (sr.contact_phone or "")
        if key:
            out[key] = sr.language or "en"
    return list(out.items())


def notify_citizen(db: Session, sr: ServiceRequest, event: str, extra: dict | None = None, *,
                   body_en: str | None = None, body_kn: str | None = None, dedupe: str | None = None) -> list[int]:
    tpl = TEMPLATES.get(event)
    ctx = _Safe(_context(db, sr, extra or {}))
    ids = []
    for recipient, lang in recipients(db, sr):
        if lang == "kn":
            body = body_kn or (tpl[1].format_map(ctx) if tpl else body_en or "")
        else:
            body = body_en or (tpl[0].format_map(ctx) if tpl else "")
        if not body:
            continue
        key = hashlib.sha1(f"{sr.id}|{event}|{recipient}|{dedupe or ''}".encode()).hexdigest()
        if db.scalar(select(Notification.id).where(Notification.dedupe_key == key)):
            continue
        n = Notification(recipient=recipient, recipient_type="CITIZEN", channel="SMS", language=lang, event=event,
                         body=body, related_sr_id=sr.id, dedupe_key=key, created_at=now())
        try:
            with db.begin_nested():
                db.add(n)
        except IntegrityError:
            continue
        ids.append(n.id)
    return ids


def notify_staff(db: Session, user_id: int, event: str, body: str, sr_id: str | None = None,
                 recipient_type: str = "OFFICER", dedupe: str | None = None) -> int | None:
    key = hashlib.sha1(f"staff|{user_id}|{event}|{sr_id}|{dedupe or body}".encode()).hexdigest()
    if db.scalar(select(Notification.id).where(Notification.dedupe_key == key)):
        return None
    n = Notification(recipient=f"user:{user_id}", recipient_type=recipient_type, channel="SMS", language="en",
                     event=event, body=body, related_sr_id=sr_id, dedupe_key=key, created_at=now())
    db.add(n)
    db.flush()
    return n.id
