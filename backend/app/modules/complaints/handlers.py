"""Deterministic (non-agent) event handlers."""
from sqlalchemy import select

from app.core.bus import Event, bus
from app.core.db import session_scope
from app.models import ServiceRequest
from app.modules.complaints.service import resolve_after_verification


def on_sr_verified(ev: Event) -> None:
    with session_scope() as db:
        sr = db.scalar(select(ServiceRequest).where(ServiceRequest.id == ev.payload["id"]))
        if sr is not None and sr.status == "VERIFIED":
            resolve_after_verification(db, sr)


def register() -> None:
    bus.subscribe("complaint.verified", on_sr_verified)
