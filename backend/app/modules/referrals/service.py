"""Inter-agency referrals (BESCOM / BWSSB). The agency side is SIMULATED via the Agency Inbox page."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.adapters.agency import agency_adapter
from app.core.bus import bus
from app.core.clock import now
from app.models import AuditLog, Referral, ServiceRequest, Timeline
from app.modules.notifications.service import notify_citizen

AGENCY_NAMES = {"BESCOM": "BESCOM (electricity)", "BWSSB": "BWSSB (water supply)", "BMRCL": "BMRCL (metro)"}


def draft_referral(db: Session, sr: ServiceRequest, agency: str, reason: str, agent_run_id: int | None = None) -> Referral:
    existing = db.scalar(select(Referral).where(Referral.sr_id == sr.id, Referral.agency == agency,
                                                Referral.status.in_(["DRAFT", "SENT"])))
    if existing:
        return existing
    r = Referral(sr_id=sr.id, agency=agency, reason=reason, status="DRAFT", created_at=now())
    db.add(r)
    db.flush()
    return r


def send_referral(db: Session, r: Referral) -> None:
    if r.status != "DRAFT":
        return
    sr = db.get(ServiceRequest, r.sr_id)
    r.status, r.sent_at = "SENT", now()
    agency_adapter.send(db, r, f"Referral for {sr.id} ({sr.category.title()}): {r.reason}")
    db.add(AuditLog(actor="system:referrals", action="referral.sent", object=f"SR:{sr.id}",
                    after_json={"referral_id": r.id, "agency": r.agency}, at=now()))
    db.add(Timeline(sr_id=sr.id, stage="Referred to Agency",
                    remarks=f"This issue needs action by {AGENCY_NAMES.get(r.agency, r.agency)}. It has been referred to them; we will follow up.",
                    remarks_kn=f"ಈ ಸಮಸ್ಯೆಗೆ {r.agency} ಕ್ರಮ ಅಗತ್ಯ. ಅವರಿಗೆ ಕಳುಹಿಸಲಾಗಿದೆ; ನಾವು ಅನುಸರಿಸುತ್ತೇವೆ.",
                    actor_type="SYSTEM"))
    notify_citizen(db, sr, "REFERRED", {"agency": AGENCY_NAMES.get(r.agency, r.agency)})
    bus.publish(db, "referral.created", {"id": r.id, "sr_id": sr.id, "agency": r.agency})


def agency_reply(db: Session, r: Referral, status: str, message: str) -> None:
    sr = db.get(ServiceRequest, r.sr_id)
    r.agency_status, r.agency_reply, r.agency_replied_at = status, message, now()
    if status == "RESOLVED":
        r.status = "CLOSED"
    agency_adapter.receive(db, r, message)
    db.add(Timeline(sr_id=sr.id, stage="Agency Update",
                    remarks=f"{r.agency} replied: {message}", remarks_kn=f"{r.agency} ಉತ್ತರ: {message}", actor_type="HUMAN"))
    notify_citizen(db, sr, "DELAY", {"reason": f"{r.agency} has replied: {message}"}, dedupe=f"reply-{r.id}-{status}")
    bus.publish(db, "referral.replied", {"id": r.id, "sr_id": sr.id, "status": status})
