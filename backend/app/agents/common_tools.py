"""Read-only lookup tools shared by several agents. All return small JSON; distances in metres."""
from __future__ import annotations

from datetime import timedelta

from rapidfuzz import fuzz
from sqlalchemy import func, select

from app.agents.runtime.tools import props, tool
from app.core.clock import now
from app.domain_config import DUPLICATE_WINDOW_HOURS, resolution_hours
from app.models import (
    Asset, AssetEvent, Attachment, KnownRoadFeature, PlannedWork, RawDetection, RoadSegment, SensitivePlace,
    ServiceRequest, SlaPolicy, User, WorkOrder,
)
from app.models.enums import Role
from app.modules import geo

LATLON = props(lat="number", lon="number")
OPEN_SR = ["SUBMITTED", "ASSIGNED", "IN_PROGRESS", "WORK_COMPLETED", "VERIFIED", "ON_HOLD", "REOPENED"]


@tool("get_ward_for_location", "Find the ward (and its ward officer) containing a location.",
      {"properties": LATLON, "required": ["lat", "lon"]})
def get_ward_for_location(ctx, lat: float, lon: float):
    w = geo.ward_for(ctx.db, lat, lon)
    if w is None:
        return {"ward": None, "inside_city": geo.in_city(ctx.db, lat, lon)}
    off = ctx.db.scalar(select(User).where(User.role == Role.WARD_OFFICER, User.ward_id == w.id))
    return {"ward_id": w.id, "ward_name": w.name, "zone": w.zone,
            "ward_officer": {"id": off.id, "name": off.name, "designation": off.designation} if off else None}


@tool("find_nearby_assets", "List municipal / utility assets (streetlights, drains, transformers, water mains) near a point.",
      {"properties": {**LATLON, **props(type={"type": "string", "enum": ["STREETLIGHT", "DRAIN", "TRANSFORMER", "WATER_MAIN", "ANY"]},
                                        radius_m=("number", "search radius, default 60"))},
       "required": ["lat", "lon"]})
def find_nearby_assets(ctx, lat: float, lon: float, type: str = "ANY", radius_m: float = 60):
    d = geo.dist_expr(Asset.location, lat, lon)
    q = select(Asset, d.label("d")).where(geo.within(Asset.location, lat, lon, min(radius_m, 500))).order_by(d).limit(8)
    if type and type != "ANY":
        q = q.where(Asset.type == type)
    return [{"asset_id": a.id, "type": a.type, "owner": a.owner, "condition": a.condition, "feeder": a.feeder,
             "distance_m": round(dist)} for a, dist in ctx.db.execute(q)]


@tool("get_asset_history", "Past complaints and repairs recorded against an asset.",
      {"properties": props(asset_id="string", days=("integer", "look-back window, default 90")), "required": ["asset_id"]})
def get_asset_history(ctx, asset_id: str, days: int = 90):
    a = ctx.db.get(Asset, asset_id)
    if a is None:
        return {"error": f"unknown asset {asset_id}"}
    since = now() - timedelta(days=days)
    evs = ctx.db.scalars(select(AssetEvent).where(AssetEvent.asset_id == asset_id, AssetEvent.date >= since)
                         .order_by(AssetEvent.date.desc())).all()
    repairs = [e for e in evs if e.type == "REPAIR"]
    return {"asset_id": a.id, "type": a.type, "owner": a.owner, "condition": a.condition, "feeder": a.feeder,
            "repairs_in_window": len(repairs), "complaints_in_window": sum(e.type == "COMPLAINT" for e in evs),
            "events": [{"date": e.date.date().isoformat(), "days_ago": (now() - e.date).days, "type": e.type,
                        "note": e.note, "crew": e.crew_id} for e in evs[:8]]}


@tool("get_asset_owner", "Who maintains an asset: MUNICIPAL, BESCOM (electricity) or BWSSB (water).",
      {"properties": props(asset_id="string"), "required": ["asset_id"]})
def get_asset_owner(ctx, asset_id: str):
    a = ctx.db.get(Asset, asset_id)
    return {"asset_id": asset_id, "owner": a.owner, "feeder": a.feeder} if a else {"error": f"unknown asset {asset_id}"}


@tool("find_nearby_open_complaints",
      "Open complaints near a point (optionally same category, within N hours). Includes text similarity to "
      "`text` if given (0-100) and whether the complaint has a photo. Excludes the complaint being analysed.",
      {"properties": {**LATLON, **props(category="string", radius_m=("number", "default 100"),
                                        hours=("integer", "only complaints created within this many hours; default 72"),
                                        text=("string", "description to compare against"))},
       "required": ["lat", "lon"]})
def find_nearby_open_complaints(ctx, lat: float, lon: float, category: str | None = None, radius_m: float = 100,
                                hours: int = DUPLICATE_WINDOW_HOURS, text: str | None = None):
    d = geo.dist_expr(ServiceRequest.location, lat, lon)
    q = (select(ServiceRequest, d.label("d")).where(geo.within(ServiceRequest.location, lat, lon, min(radius_m, 1000)),
                                                    ServiceRequest.status.in_(OPEN_SR),
                                                    ServiceRequest.created_at >= now() - timedelta(hours=hours))
         .order_by(d).limit(10))
    if category:
        q = q.where(ServiceRequest.category == category)
    if ctx.subject_id:
        q = q.where(ServiceRequest.id != ctx.subject_id)
    out = []
    for sr, dist in ctx.db.execute(q):
        out.append({"sr_id": sr.id, "category": sr.category, "status": sr.status, "priority": sr.priority,
                    "distance_m": round(dist, 1), "hours_ago": round((now() - sr.created_at).total_seconds() / 3600, 1),
                    "reporter_count": sr.reporter_count, "source": sr.source, "asset_id": sr.asset_id,
                    "text_similarity": round(fuzz.token_set_ratio(text, sr.description)) if text else None,
                    "description": sr.description[:140]})
    return out


@tool("get_planned_works", "Planned / ongoing works by other agencies (metro, pipelines, cabling) near a point.",
      {"properties": {**LATLON, **props(radius_m=("number", "default 100"))}, "required": ["lat", "lon"]})
def get_planned_works(ctx, lat: float, lon: float, radius_m: float = 100):
    today = now().date()
    q = select(PlannedWork).where(geo.within(PlannedWork.geom, lat, lon, min(radius_m, 1000)),
                                  PlannedWork.end >= today)
    return [{"name": p.name, "agency": p.agency, "start": p.start.isoformat(), "end": p.end.isoformat(),
             "active_now": p.start <= today <= p.end, "note": p.note} for p in ctx.db.scalars(q)]


@tool("get_sensitive_places_nearby", "Schools, hospitals, markets, bus stands, metro stations near a point.",
      {"properties": {**LATLON, **props(radius_m=("number", "default 200"))}, "required": ["lat", "lon"]})
def get_sensitive_places_nearby(ctx, lat: float, lon: float, radius_m: float = 200):
    d = geo.dist_expr(SensitivePlace.location, lat, lon)
    q = select(SensitivePlace, d.label("d")).where(geo.within(SensitivePlace.location, lat, lon, min(radius_m, 1000))).order_by(d).limit(6)
    return [{"name": p.name, "type": p.type, "distance_m": round(dist)} for p, dist in ctx.db.execute(q)]


@tool("get_vehicle_detections_nearby",
      "Connected-vehicle road-hazard detections (SIMULATED OEM feed) near a point: count and distinct vehicles.",
      {"properties": {**LATLON, **props(radius_m=("number", "default 30"), days=("integer", "default 14"))},
       "required": ["lat", "lon"]})
def get_vehicle_detections_nearby(ctx, lat: float, lon: float, radius_m: float = 30, days: int = 14):
    q = select(func.count(), func.count(func.distinct(RawDetection.vehicle_ref)), func.avg(RawDetection.confidence),
               func.max(RawDetection.detected_at)).where(
        geo.within(RawDetection.location, lat, lon, min(radius_m, 200)),
        RawDetection.detected_at >= now() - timedelta(days=days))
    n, vehicles, conf, last = ctx.db.execute(q).one()
    return {"detections": n, "distinct_vehicles": vehicles, "avg_confidence": round(conf, 2) if conf else None,
            "last_seen": last.isoformat() if last else None}


@tool("get_road_class", "Is the nearest road ARTERIAL or LOCAL (and its name)?",
      {"properties": LATLON, "required": ["lat", "lon"]})
def get_road_class(ctx, lat: float, lon: float):
    d = geo.dist_expr(RoadSegment.geom, lat, lon)
    row = ctx.db.execute(select(RoadSegment, d.label("d")).order_by(d).limit(1)).first()
    if row is None or row.d > 80:
        return {"road_class": "LOCAL", "road": None, "distance_m": round(row.d) if row else None}
    return {"road_class": row[0].road_class, "road": row[0].name, "distance_m": round(row.d)}


@tool("check_known_features", "Known speed breakers / railway crossings near a point (these cause false pothole jolts).",
      {"properties": {**LATLON, **props(radius_m=("number", "default 20"))}, "required": ["lat", "lon"]})
def check_known_features(ctx, lat: float, lon: float, radius_m: float = 20):
    d = geo.dist_expr(KnownRoadFeature.location, lat, lon)
    q = select(KnownRoadFeature, d.label("d")).where(geo.within(KnownRoadFeature.location, lat, lon, min(radius_m, 200))).order_by(d)
    return [{"type": f.type, "name": f.name, "distance_m": round(dist, 1)} for f, dist in ctx.db.execute(q)]


@tool("get_sla_policy", "Resolution time (hours) for a category and priority.",
      {"properties": props(category="string", priority={"type": "string", "enum": ["P1", "P2", "P3", "P4"]}),
       "required": ["category", "priority"]})
def get_sla_policy(ctx, category: str, priority: str):
    p = ctx.db.scalar(select(SlaPolicy).where(SlaPolicy.category == category, SlaPolicy.priority == priority))
    hours = p.resolution_hours if p else resolution_hours(category, priority)
    return {"category": category, "priority": priority, "resolution_hours": hours,
            "resolution_days": round(hours / 24, 1), "verification_hours": p.verification_hours if p else 168}


@tool("get_officer_workload", "Open complaint counts for the ward officer(s) of a ward (optionally one department).",
      {"properties": props(ward_id="string", department_id="string"), "required": ["ward_id"]})
def get_officer_workload(ctx, ward_id: str, department_id: str | None = None):
    out = []
    for u in ctx.db.scalars(select(User).where(User.role == Role.WARD_OFFICER, User.ward_id == ward_id)):
        q = select(func.count()).select_from(ServiceRequest).where(ServiceRequest.owner_id == u.id,
                                                                   ServiceRequest.status.in_(OPEN_SR))
        if department_id:
            q = q.where(ServiceRequest.department_id == department_id)
        out.append({"officer_id": u.id, "name": u.name, "designation": u.designation, "open_cases": ctx.db.scalar(q)})
    return out


@tool("get_recent_repairs", "Work orders VERIFIED (repairs completed) near a point within N days.",
      {"properties": {**LATLON, **props(radius_m=("number", "default 25"), days=("integer", "default 30"))},
       "required": ["lat", "lon"]})
def get_recent_repairs(ctx, lat: float, lon: float, radius_m: float = 25, days: int = 30):
    d = geo.dist_expr(ServiceRequest.location, lat, lon)
    q = (select(WorkOrder, ServiceRequest, d.label("d")).join(ServiceRequest, ServiceRequest.id == WorkOrder.sr_id)
         .where(WorkOrder.status == "VERIFIED", WorkOrder.verified_at >= now() - timedelta(days=days),
                geo.within(ServiceRequest.location, lat, lon, min(radius_m, 200))).order_by(d).limit(5))
    return [{"wo_id": w.id, "sr_id": s.id, "category": s.category, "crew_id": w.crew_id,
             "verified_days_ago": round((now() - w.verified_at).total_seconds() / 86400, 1), "distance_m": round(dist, 1)}
            for w, s, dist in ctx.db.execute(q)]


def photo_ids(db, sr_id: str) -> list[int]:
    return list(db.scalars(select(Attachment.id).where(Attachment.sr_id == sr_id, Attachment.kind == "CITIZEN")))
