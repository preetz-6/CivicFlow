"""Merging duplicates keeps every reporter subscribed to the parent's updates."""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.actor import Actor
from app.core.errors import DomainError
from app.models import ServiceRequest, SrReporter, Timeline
from app.modules.notifications.service import notify_citizen
from app.modules.workflow.service import transition

PRIORITY_ORDER = ["P1", "P2", "P3", "P4"]


def merge_into(db: Session, dup: ServiceRequest, parent: ServiceRequest, actor: Actor, *,
               confidence: float | None = None, note: str | None = None) -> None:
    if dup.id == parent.id:
        raise DomainError("Cannot merge a grievance into itself")
    while parent.status == "MERGED" and parent.parent_sr_id:  # always merge into the root
        parent = db.get(ServiceRequest, parent.parent_sr_id)
    if parent.status in ("CLOSED", "REJECTED"):
        raise DomainError(f"{parent.id} is already {parent.status.lower()}")
    transition(db, dup, "MERGED", actor, parent_sr_id=parent.id,
               reason=note or (f"Duplicate (confidence {confidence:.2f})" if confidence is not None else "Duplicate"),
               meta={"confidence": confidence} if confidence is not None else None)
    for r in db.scalars(select(SrReporter).where(SrReporter.sr_id == dup.id)):
        db.add(SrReporter(sr_id=parent.id, citizen_user_id=r.citizen_user_id, contact_name=r.contact_name,
                          contact_phone=r.contact_phone, language=r.language, merged_from_sr_id=dup.id))
    db.flush()
    parent.reporter_count = db.scalar(select(func.count()).select_from(SrReporter).where(SrReporter.sr_id == parent.id)) or 1
    # more reporters -> a more urgent problem: P4->P3 at 2 reporters, ->P2 at 3+
    target = "P2" if parent.reporter_count >= 3 else ("P3" if parent.reporter_count >= 2 else parent.priority)
    if PRIORITY_ORDER.index(target) < PRIORITY_ORDER.index(parent.priority):
        parent.priority = target
        from app.modules.complaints.service import apply_sla

        apply_sla(db, parent)
    n_others = parent.reporter_count - 1
    db.add(Timeline(sr_id=parent.id, stage="Similar Report Linked",
                    remarks=f"System linked {n_others} similar report{'s' if n_others != 1 else ''} to this grievance "
                            f"({parent.reporter_count} citizens reported the same issue).",
                    remarks_kn=f"ಇದೇ ಸಮಸ್ಯೆಯ {n_others} ದೂರುಗಳನ್ನು ವ್ಯವಸ್ಥೆ ಜೋಡಿಸಿದೆ ({parent.reporter_count} ನಾಗರಿಕರು ವರದಿ ಮಾಡಿದ್ದಾರೆ).",
                    actor_type=str(actor.kind)))
    notify_citizen(db, dup, "MERGED", {"parent": parent.id, "count": parent.reporter_count})


def unmerge(db: Session, sr: ServiceRequest, actor: Actor, reason: str) -> None:
    parent_id = sr.parent_sr_id
    transition(db, sr, "SUBMITTED", actor, reason=reason)
    if parent_id:
        parent = db.get(ServiceRequest, parent_id)
        for r in db.scalars(select(SrReporter).where(SrReporter.sr_id == parent_id, SrReporter.merged_from_sr_id == sr.id)):
            db.delete(r)
        db.flush()
        parent.reporter_count = max(1, db.scalar(select(func.count()).select_from(SrReporter).where(SrReporter.sr_id == parent_id)) or 1)
