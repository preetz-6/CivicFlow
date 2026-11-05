"""Road Hazard Map + review queue + data sources (Control Room)."""
from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.actor import Actor
from app.core.clock import now
from app.core.db import get_db
from app.core.security import require_roles
from app.models import DataSource, HazardCluster, KnownRoadFeature, RawDetection, RejectedDetection, ServiceRequest
from app.models.enums import Role
from app.modules import geo

router = APIRouter(tags=["hazards"])
STAFF = (Role.CONTROL_ROOM, Role.WARD_OFFICER)


def cluster_out(h: HazardCluster) -> dict:
    lat, lon = geo.latlon(h.center)
    return {"id": h.id, "lat": lat, "lon": lon, "status": h.status, "hazard_type": h.hazard_type,
            "detections": h.n_detections, "distinct_vehicles": h.distinct_vehicles, "avg_confidence": h.avg_confidence,
            "avg_jolt_g": h.avg_jolt_g, "days_seen": h.days_seen, "first_seen": h.first_seen, "last_seen": h.last_seen,
            "filter_reason": h.filter_reason, "decision_reason": h.decision_reason, "sr_id": h.sr_id,
            "flagged_wo_id": h.flagged_wo_id, "agent_run_id": h.agent_run_id}


@router.get("/hazards/map")
def hazard_map(raw: bool = True, days: int = 14, db: Session = Depends(get_db), actor: Actor = Depends(require_roles(*STAFF))):
    since = now() - timedelta(days=days)
    out = {"clusters": [cluster_out(h) for h in db.scalars(select(HazardCluster).order_by(HazardCluster.id))],
           "known_features": [{"type": f.type, "name": f.name, **dict(zip(("lat", "lon"), geo.latlon(f.location)))}
                              for f in db.scalars(select(KnownRoadFeature))],
           "complaints": [], "raw": [], "simulated_source": True}
    srs = db.scalars(select(ServiceRequest).where(
        (ServiceRequest.source == "VEHICLE_FEED") | (ServiceRequest.corroboration_count > 0))
        .where(ServiceRequest.status.notin_(["MERGED", "REJECTED"])))
    for s in srs:
        lat, lon = geo.latlon(s.location)
        out["complaints"].append({"id": s.id, "lat": lat, "lon": lon, "source": s.source, "status": s.status,
                                  "priority": s.priority, "vehicles": s.corroboration_count, "category": s.category})
    if raw:
        for d in db.scalars(select(RawDetection).where(RawDetection.detected_at >= since)
                            .order_by(RawDetection.id.desc()).limit(4000)):
            lat, lon = geo.latlon(d.location)
            out["raw"].append({"lat": lat, "lon": lon, "c": round(d.confidence, 2), "cluster_id": d.cluster_id})
    return out


@router.get("/hazards/clusters")
def clusters(status: str | None = None, db: Session = Depends(get_db), actor: Actor = Depends(require_roles(*STAFF))):
    q = select(HazardCluster).order_by(HazardCluster.distinct_vehicles.desc())
    if status:
        q = q.where(HazardCluster.status.in_(status.split(",")))
    return [cluster_out(h) for h in db.scalars(q)]


class DismissIn(BaseModel):
    reason: str = Field(min_length=3)


@router.post("/hazards/clusters/{cid}/confirm")
def confirm(cid: int, db: Session = Depends(get_db), actor: Actor = Depends(require_roles(*STAFF))):
    """Officer confirms a REVIEW cluster -> system complaint (then Case Investigator)."""
    from app.agents.runtime.tools import ToolContext
    from app.agents.sensing import create_system_complaint

    h = db.get(HazardCluster, cid)
    if h is None or h.status != "REVIEW":
        raise HTTPException(409, "Only clusters in the review queue can be confirmed")
    ctx = ToolContext(db=db, run_id=0, agent="officer", actor=actor)
    res = create_system_complaint(ctx, cid, note=f"Confirmed from the review queue by {actor.label}.")
    h.decision_reason = (h.decision_reason or "") + f" | Confirmed by {actor.label}"
    db.commit()
    return res


@router.post("/hazards/clusters/{cid}/dismiss")
def dismiss(cid: int, body: DismissIn, db: Session = Depends(get_db), actor: Actor = Depends(require_roles(*STAFF))):
    h = db.get(HazardCluster, cid)
    if h is None or h.status not in ("REVIEW", "NEW"):
        raise HTTPException(409, "Only new or review clusters can be dismissed")
    h.status, h.decision_reason = "IGNORED", f"Dismissed by {actor.label}: {body.reason}"
    db.commit()
    return {"status": h.status}


@router.get("/data-sources")
def data_sources(db: Session = Depends(get_db), actor: Actor = Depends(require_roles(*STAFF))):
    out = []
    for s in db.scalars(select(DataSource).order_by(DataSource.id)):
        recent = db.scalars(select(RejectedDetection).where(RejectedDetection.source_id == s.id)
                            .order_by(RejectedDetection.id.desc()).limit(5)).all()
        out.append({"id": s.id, "name": s.name, "kind": s.kind, "simulated": s.simulated,
                    "last_ingested_at": s.last_ingested_at, "accepted": s.accepted_count, "rejected": s.rejected_count,
                    "recent_rejections": [{"at": r.at, "source_record_id": r.source_record_id, "reason": r.reason} for r in recent]})
    return out
