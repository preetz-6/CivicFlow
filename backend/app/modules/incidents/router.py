"""Incidents (Surge Commander) + the SIMULATED weather adapter."""
from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.core.actor import Actor
from app.core.clock import now
from app.core.db import get_db
from app.core.security import require_roles
from app.models import AuditLog, Incident, ServiceRequest, WeatherAlert
from app.models.enums import Role
from app.modules import geo

router = APIRouter(tags=["incidents"])
STAFF = (Role.CONTROL_ROOM, Role.WARD_OFFICER)


def out(db, i: Incident) -> dict:
    lat, lon = geo.latlon(i.center)
    resolved = db.scalar(select(func.count()).select_from(ServiceRequest).where(
        ServiceRequest.incident_id == i.id, ServiceRequest.status.in_(["RESOLVED", "CLOSED"]))) or 0
    # citizens who reported it, including duplicates merged into the linked grievances
    reports = db.scalar(select(func.sum(ServiceRequest.reporter_count)).where(ServiceRequest.incident_id == i.id)) or 0
    return {"id": i.id, "name": i.name, "display_name": f"{i.name} — {reports} reports", "category": i.category,
            "severity": i.severity, "status": i.status, "report_count": reports, "unique_issues": i.report_count,
            "resolved_count": resolved,
            "lat": lat, "lon": lon, "crew_suggestion": i.crew_suggestion, "advisory_draft": i.advisory_draft,
            "advisory_draft_kn": i.advisory_draft_kn, "advisory_published": i.advisory_published,
            "published_at": i.published_at, "summary": i.summary, "summary_at": i.summary_at,
            "agent_run_id": i.agent_run_id, "created_at": i.created_at,
            "sr_ids": list(db.scalars(select(ServiceRequest.id).where(ServiceRequest.incident_id == i.id)))}


@router.get("/incidents")
def incidents(status: str | None = None, db: Session = Depends(get_db), actor: Actor = Depends(require_roles(*STAFF))):
    q = select(Incident).order_by(Incident.id.desc())
    if status:
        q = q.where(Incident.status == status)
    return [out(db, i) for i in db.scalars(q)]


class PublishIn(BaseModel):
    advisory: str | None = Field(None, max_length=300, description="Edited advisory text (optional)")
    advisory_kn: str | None = Field(None, max_length=300)


@router.post("/incidents/{iid}/publish")
def publish(iid: int, body: PublishIn | None = None, db: Session = Depends(get_db),
            actor: Actor = Depends(require_roles(Role.CONTROL_ROOM))):
    """Human-only: the drafted advisory goes to the public 'What's New' ticker."""
    i = db.get(Incident, iid)
    if i is None:
        raise HTTPException(404)
    before = {"advisory": i.advisory_draft, "published": i.advisory_published}
    if body and body.advisory:
        i.advisory_draft = body.advisory
    if body and body.advisory_kn:
        i.advisory_draft_kn = body.advisory_kn
    if not i.advisory_draft:
        raise HTTPException(409, "No advisory text to publish")
    i.advisory_published, i.published_at, i.published_by = True, now(), actor.user_id
    db.add(AuditLog(actor=actor.id, action="incident.publish_advisory", object=f"INCIDENT:{i.id}", before_json=before,
                    after_json={"advisory": i.advisory_draft}, at=now()))
    db.commit()
    return out(db, i)


@router.post("/incidents/{iid}/close")
def close(iid: int, db: Session = Depends(get_db), actor: Actor = Depends(require_roles(Role.CONTROL_ROOM))):
    i = db.get(Incident, iid)
    if i is None:
        raise HTTPException(404)
    i.status = "CLOSED"
    db.commit()
    return out(db, i)


# ------------------------------------------------------------------ simulated weather adapter
class AlertIn(BaseModel):
    title: str = "Heavy rain warning (IMD orange alert) - SIMULATED"
    severity: str = "ORANGE"
    area_name: str | None = "Bengaluru West"
    hours: float = 6


@router.get("/weather/alerts")
def weather_alerts(db: Session = Depends(get_db)):
    return [{"id": a.id, "title": a.title, "severity": a.severity, "area_name": a.area_name, "active": a.active,
             "issued_at": a.issued_at, "expires_at": a.expires_at, "simulated": True}
            for a in db.scalars(select(WeatherAlert).order_by(WeatherAlert.id.desc()).limit(10))]


@router.post("/demo/weather-alert")
def raise_alert(body: AlertIn, db: Session = Depends(get_db)):
    """DEMO ONLY (used by the simulator's rain scenario)."""
    if not settings.demo_mode:
        raise HTTPException(404)
    a = WeatherAlert(title=body.title, severity=body.severity, area_name=body.area_name, active=True, issued_at=now(),
                     expires_at=now() + timedelta(hours=body.hours))
    db.add(a)
    db.commit()
    return {"id": a.id}


@router.post("/demo/weather-alert/clear")
def clear_alerts(db: Session = Depends(get_db)):
    if not settings.demo_mode:
        raise HTTPException(404)
    for a in db.scalars(select(WeatherAlert).where(WeatherAlert.active.is_(True))):
        a.active = False
    db.commit()
    return {"ok": True}
