"""Agent 3: Road Hazard Sensing. Trigger: scheduler (every ~60 s) when new raw detections arrived.

Pipeline: raw_detections -> PostGIS ST_ClusterDBSCAN (deterministic) -> hazard_clusters -> filters
(known speed breakers / rail crossings, single-vehicle) -> agent decides on new/changed clusters:
CREATE system complaint | CORROBORATE an open citizen complaint | REPAIR_FAILURE | REVIEW | IGNORE.
Deterministic guards in apply(): a system complaint is created only for a STRONG cluster
(>= 3 distinct vehicles, avg confidence >= 0.8) with no open complaint within 25 m.
"""
from __future__ import annotations

from datetime import timedelta
from typing import Literal

from pydantic import BaseModel, Field
from sqlalchemy import func, select, text

from app.agents import common_tools  # noqa: F401
from app.agents.runtime.base import Agent
from app.agents.runtime.tools import ToolContext, note, props, tool
from app.core.clock import now
from app.models import (
    Crew, HazardCluster, KnownRoadFeature, RawDetection, ServiceRequest, SystemState, Timeline, User, WorkOrder,
)
from app.modules import geo
from app.modules.notifications.service import notify_citizen, notify_staff

WINDOW_DAYS = 14
EPS_M = 12.0
MATCH_M = 15.0
FEATURE_M = 15.0
CORROBORATE_M = 25.0
STRONG_VEHICLES = 3
STRONG_CONF = 0.8
MAX_PER_RUN = 25
CURSOR_KEY = "sensing_cursor"


# ----------------------------------------------------------------------------- deterministic clustering
CLUSTER_SQL = text("""
WITH pts AS (
  SELECT id, vehicle_ref, confidence, vertical_accel_peak_g AS jolt, detected_at, location, hazard_type,
         ST_ClusterDBSCAN(ST_Transform(location, 32643), eps := :eps, minpoints := 2) OVER () AS cid
  FROM raw_detections WHERE detected_at >= :since
)
SELECT cid, array_agg(id) AS ids, count(*) AS n, count(DISTINCT vehicle_ref) AS vehicles,
       avg(confidence) AS conf, avg(jolt) AS jolt, min(detected_at) AS first_seen, max(detected_at) AS last_seen,
       count(DISTINCT (detected_at AT TIME ZONE 'Asia/Kolkata')::date) AS days,
       ST_Y(ST_Centroid(ST_Collect(location))) AS lat, ST_X(ST_Centroid(ST_Collect(location))) AS lon,
       mode() WITHIN GROUP (ORDER BY hazard_type) AS hazard
FROM pts WHERE cid IS NOT NULL GROUP BY cid
""")


def recluster(db) -> dict:
    """Run DBSCAN over the window and upsert persistent hazard_clusters. Returns counts."""
    stats = {"clusters": 0, "new": 0, "filtered": 0}
    for r in db.execute(CLUSTER_SQL, {"eps": EPS_M, "since": now() - timedelta(days=WINDOW_DAYS)}):
        stats["clusters"] += 1
        d = geo.dist_expr(HazardCluster.center, r.lat, r.lon)
        hc = db.scalar(select(HazardCluster).where(geo.within(HazardCluster.center, r.lat, r.lon, MATCH_M)).order_by(d).limit(1))
        if hc is None:
            hc = HazardCluster(center=geo.make_point(r.lat, r.lon), status="NEW", created_at=now(),
                               n_detections=0, distinct_vehicles=0, avg_confidence=0, first_seen=r.first_seen,
                               last_seen=r.last_seen)
            db.add(hc)
            stats["new"] += 1
        grew = r.vehicles > (hc.distinct_vehicles or 0)
        hc.center = geo.make_point(r.lat, r.lon)
        hc.n_detections, hc.distinct_vehicles = r.n, r.vehicles
        hc.avg_confidence, hc.avg_jolt_g = round(float(r.conf), 3), round(float(r.jolt), 2) if r.jolt else None
        hc.first_seen, hc.last_seen, hc.days_seen, hc.hazard_type = r.first_seen, r.last_seen, r.days, r.hazard
        hc.updated_at = now()
        db.flush()
        db.execute(RawDetection.__table__.update().where(RawDetection.id.in_(r.ids)).values(cluster_id=hc.id))
        # deterministic filters
        feat = db.execute(select(KnownRoadFeature, geo.dist_expr(KnownRoadFeature.location, r.lat, r.lon).label("d"))
                          .where(geo.within(KnownRoadFeature.location, r.lat, r.lon, FEATURE_M)).limit(1)).first()
        if feat is not None:
            if hc.status != "FILTERED":
                stats["filtered"] += 1
            hc.status = "FILTERED"
            kind = "speed breaker" if feat[0].type == "SPEED_BREAKER" else "railway crossing"
            hc.filter_reason = f"Known {kind}: {feat[0].name} ({feat.d:.0f} m)"
            continue
        if r.vehicles < 2:
            if hc.status in ("NEW", "FILTERED"):
                hc.status, hc.filter_reason = "FILTERED", "Single vehicle only (possible one-off jolt)"
            continue
        if hc.status == "FILTERED" and hc.filter_reason and hc.filter_reason.startswith("Single vehicle"):
            hc.status, hc.filter_reason = "NEW", None  # a second vehicle confirmed it
        if grew and hc.status in ("CORROBORATED", "CREATED") and hc.sr_id:
            sr = db.get(ServiceRequest, hc.sr_id)
            if sr:
                sr.corroboration_count = max(sr.corroboration_count or 0, r.vehicles)
    return stats


def candidates(db) -> list[HazardCluster]:
    strong_review = (HazardCluster.status == "REVIEW") & (HazardCluster.distinct_vehicles >= STRONG_VEHICLES) & (
        HazardCluster.avg_confidence >= STRONG_CONF)
    return list(db.scalars(select(HazardCluster).where((HazardCluster.status == "NEW") | strong_review)
                           .order_by(HazardCluster.distinct_vehicles.desc(), HazardCluster.id).limit(MAX_PER_RUN)))


def cluster_view(hc: HazardCluster) -> dict:
    lat, lon = geo.latlon(hc.center)
    return {"cluster_id": hc.id, "lat": lat, "lon": lon, "hazard_type": hc.hazard_type, "detections": hc.n_detections,
            "distinct_vehicles": hc.distinct_vehicles, "avg_confidence": hc.avg_confidence, "avg_jolt_g": hc.avg_jolt_g,
            "days_seen": hc.days_seen, "status": hc.status,
            "strong": hc.distinct_vehicles >= STRONG_VEHICLES and hc.avg_confidence >= STRONG_CONF}


# ----------------------------------------------------------------------------- tools
@tool("cluster_detections", "Current hazard clusters from connected-vehicle detections (DBSCAN, last 14 days). "
      "Read-only summary; clustering itself runs automatically before you are called.",
      {"properties": props(status=("string", "optional filter: NEW, REVIEW, FILTERED, CREATED, CORROBORATED, REPAIR_FAILURE"))})
def cluster_detections(ctx, status: str | None = None):
    q = select(HazardCluster).order_by(HazardCluster.id).limit(40)
    if status:
        q = q.where(HazardCluster.status == status)
    return [{**cluster_view(h), "filter_reason": h.filter_reason, "sr_id": h.sr_id} for h in ctx.db.scalars(q)]


@tool("get_cluster_stats", "Distinct vehicles, detections, days seen, average confidence and jolt for one cluster.",
      {"properties": props(cluster_id="integer"), "required": ["cluster_id"]})
def get_cluster_stats(ctx, cluster_id: int):
    hc = ctx.db.get(HazardCluster, cluster_id)
    if hc is None:
        return {"error": f"no cluster {cluster_id}"}
    speeds = ctx.db.execute(select(func.avg(RawDetection.speed_kmph), func.max(RawDetection.vertical_accel_peak_g))
                            .where(RawDetection.cluster_id == cluster_id)).one()
    return {**cluster_view(hc), "avg_speed_kmph": round(speeds[0], 1) if speeds[0] else None,
            "max_jolt_g": speeds[1], "filter_reason": hc.filter_reason}


# ----------------------------------------------------------------------------- actions (called from apply)
def _road(ctx, lat, lon) -> dict:
    return ctx.call("get_road_class", {"lat": lat, "lon": lon}, by="apply")


@tool("create_system_complaint", "Create a complaint from a strong cluster (source VEHICLE_FEED). It then goes through "
      "the Case Investigator like any citizen complaint.", {"properties": props(cluster_id="integer", note="string"),
                                                             "required": ["cluster_id"]})
def create_system_complaint(ctx, cluster_id: int, note: str | None = None):
    from app.modules.complaints.service import create_complaint

    hc = ctx.db.get(HazardCluster, cluster_id)
    lat, lon = geo.latlon(hc.center)
    road = _road(ctx, lat, lon)
    cat = "DAMAGED_ROAD" if hc.hazard_type == "DAMAGED_ROAD" else "POTHOLE"
    where = f" on {road['road']}" if road.get("road") else ""
    desc = (f"{'Pothole' if cat == 'POTHOLE' else 'Road damage'} detected{where} by {hc.distinct_vehicles} connected "
            f"vehicles over {hc.days_seen} day(s) (avg confidence {hc.avg_confidence:.2f}"
            + (f", avg jolt {hc.avg_jolt_g:.1f} g" if hc.avg_jolt_g else "") + "). No citizen report yet."
            + (f" {note}" if note else ""))
    sr = create_complaint(ctx.db, category=cat, description=desc, lat=lat, lon=lon, anonymous=True,
                          source="VEHICLE_FEED", actor=ctx.actor)
    sr.corroboration_count = hc.distinct_vehicles
    hc.status, hc.sr_id = "CREATED", sr.id
    return {"sr_id": sr.id, "category": cat, "ward_id": sr.ward_id}


@tool("attach_corroboration", "Attach a cluster to an open citizen complaint as corroboration ('Confirmed by N vehicles').",
      {"properties": props(sr_id="string", cluster_id="integer"), "required": ["sr_id", "cluster_id"]})
def attach_corroboration(ctx, sr_id: str, cluster_id: int):
    from app.models import AuditLog
    from app.modules.complaints.service import apply_sla

    sr = ctx.db.get(ServiceRequest, sr_id)
    hc = ctx.db.get(HazardCluster, cluster_id)
    while sr.status == "MERGED" and sr.parent_sr_id:
        sr = ctx.db.get(ServiceRequest, sr.parent_sr_id)
    n = hc.distinct_vehicles
    sr.corroboration_count = max(sr.corroboration_count or 0, n)
    sr.priority_score = round((sr.priority_score or 0) + min(n, 10) * 0.5, 2)
    raised = None
    if n >= 5 and sr.priority in ("P3", "P4"):
        old = sr.priority
        sr.priority = "P2" if old == "P3" else "P3"
        apply_sla(ctx.db, sr)
        raised = sr.priority
        ctx.db.add(AuditLog(actor=ctx.actor.id, action="SR.priority_corroborated", object=f"SR:{sr.id}",
                            before_json={"priority": old}, after_json={"priority": sr.priority, "vehicles": n}, at=now()))
    hc.status, hc.sr_id = "CORROBORATED", sr.id
    ctx.db.add(Timeline(sr_id=sr.id, stage="Confirmed by Road Data",
                        remarks=f"Confirmed by {n} connected vehicles that detected the same pothole.",
                        remarks_kn=f"{n} ಸಂಪರ್ಕಿತ ವಾಹನಗಳು ಇದೇ ರಸ್ತೆ ಗುಂಡಿಯನ್ನು ದೃಢಪಡಿಸಿವೆ.", actor_type="AGENT", at=now()))
    notify_citizen(ctx.db, sr, "CORROBORATED", {"vehicles": n}, dedupe=str(cluster_id))
    return {"sr_id": sr.id, "vehicles": n, "priority_raised_to": raised}


@tool("flag_repair_failure", "Flag a recently verified repair as possibly failed; mark the crew for quality review.",
      {"properties": props(wo_id="string", cluster_id="integer"), "required": ["wo_id", "cluster_id"]})
def flag_repair_failure(ctx, wo_id: str, cluster_id: int):
    wo = ctx.db.get(WorkOrder, wo_id)
    hc = ctx.db.get(HazardCluster, cluster_id)
    crew = ctx.db.get(Crew, wo.crew_id)
    crew.audit_priority = "HIGH"
    hc.status, hc.flagged_wo_id = "REPAIR_FAILURE", wo.id
    days = (now() - wo.verified_at).days if wo.verified_at else None
    for u in ctx.db.scalars(select(User).where(User.role == "CONTROL_ROOM")):
        notify_staff(ctx.db, u.id, "REPAIR_FAILURE",
                     f"Possible failed repair: {wo.id} by crew {wo.crew_id} (verified {days} days ago) is being hit again by "
                     f"{hc.distinct_vehicles} vehicles. Crew marked for quality review.", wo.sr_id, "CONTROL", dedupe=str(cluster_id))
    res = create_system_complaint(ctx, cluster_id, note=f"Same spot was repaired under {wo.id} {days} days ago (possible repair failure).")
    hc.status = "REPAIR_FAILURE"
    return {"wo_id": wo.id, "crew_id": wo.crew_id, "crew_audit_priority": "HIGH", "new_sr_id": res["sr_id"]}


@tool("queue_for_review", "Put an ambiguous cluster in the officer review queue with your reasoning.",
      {"properties": props(cluster_id="integer", reason="string"), "required": ["cluster_id", "reason"]})
def queue_for_review(ctx, cluster_id: int, reason: str):
    hc = ctx.db.get(HazardCluster, cluster_id)
    hc.status, hc.decision_reason = "REVIEW", reason
    return {"cluster_id": cluster_id, "status": "REVIEW"}


# ----------------------------------------------------------------------------- agent
class Decision(BaseModel):
    cluster_id: int
    decision: Literal["CREATE", "CORROBORATE", "REPAIR_FAILURE", "REVIEW", "IGNORE"]
    reason: str
    sr_id: str | None = Field(None, description="open complaint to corroborate (CORROBORATE)")
    wo_id: str | None = Field(None, description="recent repair that failed (REPAIR_FAILURE)")


class SensingReport(BaseModel):
    decisions: list[Decision]
    summary: str
    confidence: float = Field(ge=0, le=1)


SYSTEM = f"""You are the Road Hazard Sensing analyst for CivicFlow Municipal Corporation. Connected two-wheelers
(SIMULATED OEM feed) report sharp vertical jolts. They have already been clustered (DBSCAN, {EPS_M:.0f} m) and clusters on
known speed breakers, railway crossings and single-vehicle clusters were filtered out automatically.
For EACH candidate cluster decide exactly one of:
- CORROBORATE (give sr_id): an OPEN citizen pothole/road complaint within {CORROBORATE_M:.0f} m. Check this first.
- REPAIR_FAILURE (give wo_id): a repair VERIFIED at this spot in the last 30 days (get_recent_repairs).
- CREATE: a strong cluster (>= {STRONG_VEHICLES} distinct vehicles AND avg confidence >= {STRONG_CONF}) with no complaint nearby.
- REVIEW: weak or ambiguous (few vehicles, low confidence, odd jolt pattern); explain why for the officer.
- IGNORE: clearly not a road defect.
Use check_known_features as a sanity check. Mention arterial roads (get_road_class) in the reason when relevant.
summary: one or two sentences for the Control Room."""


class RoadHazardSensing(Agent):
    name = "sensing"
    label = "Road Hazard Sensing"
    system_prompt = SYSTEM
    triggers: list[str] = []  # scheduler-driven
    output_model = SensingReport
    subject_type = "CLUSTER"
    max_steps = 10
    timeout_s = 90.0
    tools = ["cluster_detections", "get_cluster_stats", "check_known_features", "find_nearby_open_complaints",
             "get_recent_repairs", "get_road_class"]

    def build_input(self, db, payload):
        cursor = db.get(SystemState, CURSOR_KEY)
        last = (cursor.value or {}).get("max_id", 0) if cursor else 0
        max_id = db.scalar(select(func.max(RawDetection.id))) or 0
        if max_id <= last and not payload.get("force"):
            if not candidates(db):  # nothing new and nothing left over from a capped previous run
                return None
            stats = {"clusters": 0, "new": 0, "filtered": 0, "note": "leftover candidates from previous run"}
        else:
            stats = recluster(db)
        if cursor:
            cursor.value = {"max_id": max_id}
        else:
            db.add(SystemState(key=CURSOR_KEY, value={"max_id": max_id}))
        cands = candidates(db)
        if not cands:
            return None
        return {"subject_id": f"{len(cands)} clusters", "recluster": stats,
                "candidates": [cluster_view(c) for c in cands], "_ids": [c.id for c in cands]}

    def decision(self, out: SensingReport) -> str:
        from collections import Counter

        c = Counter(d.decision for d in out.decisions)
        return ", ".join(f"{k.lower().replace('_', ' ')} {v}" for k, v in c.most_common())

    def rationale(self, out: SensingReport) -> str:
        return "\n".join([out.summary] + [f"- Cluster {d.cluster_id}: {d.decision} - {d.reason}" for d in out.decisions])

    # --- the same thresholds as pure rules
    def rule_decide(self, ctx: ToolContext, hc: HazardCluster) -> Decision:
        lat, lon = geo.latlon(hc.center)
        v = cluster_view(hc)
        opens = [c for c in ctx.call("find_nearby_open_complaints", {"lat": lat, "lon": lon, "radius_m": CORROBORATE_M,
                                                                       "hours": 24 * 60}, by="rules")
                 if c["category"] in ("POTHOLE", "DAMAGED_ROAD")]
        if opens:
            c = opens[0]
            return Decision(cluster_id=hc.id, decision="CORROBORATE", sr_id=c["sr_id"],
                            reason=f"Open complaint {c['sr_id']} {c['distance_m']:.0f} m away; {v['distinct_vehicles']} vehicles confirm it.")
        reps = ctx.call("get_recent_repairs", {"lat": lat, "lon": lon, "radius_m": CORROBORATE_M, "days": 30}, by="rules")
        if reps:
            r = reps[0]
            return Decision(cluster_id=hc.id, decision="REPAIR_FAILURE", wo_id=r["wo_id"],
                            reason=f"Repaired under {r['wo_id']} by crew {r['crew_id']} {r['verified_days_ago']:.0f} days ago; "
                                   f"{v['distinct_vehicles']} vehicles hit it again.")
        if v["strong"]:
            road = ctx.call("get_road_class", {"lat": lat, "lon": lon}, by="rules")
            on = f" on {road['road']} ({road['road_class'].lower()})" if road.get("road") else ""
            return Decision(cluster_id=hc.id, decision="CREATE",
                            reason=f"{v['distinct_vehicles']} distinct vehicles, avg confidence {v['avg_confidence']:.2f}{on}; no complaint nearby.")
        return Decision(cluster_id=hc.id, decision="REVIEW",
                        reason=f"Weak signal: {v['distinct_vehicles']} vehicles, avg confidence {v['avg_confidence']:.2f}. "
                               f"Needs a look before creating a complaint.")

    def fallback(self, ctx, inp):
        ds = [self.rule_decide(ctx, ctx.db.get(HazardCluster, cid)) for cid in inp["_ids"]]
        return SensingReport(decisions=ds, confidence=0.85,
                             summary=f"{len(ds)} new clusters checked; {inp['recluster']['filtered']} filtered as known road features.")

    def apply(self, ctx, inp, out: SensingReport):
        by_id = {d.cluster_id: d for d in out.decisions}
        final = []
        for cid in inp["_ids"]:
            hc = ctx.db.get(HazardCluster, cid)
            if hc is None or hc.status not in ("NEW", "REVIEW"):
                continue
            d = by_id.get(cid)
            rule = self.rule_decide(ctx, hc)
            if d is None:
                d = rule
            elif d.decision == "CREATE" and rule.decision != "CREATE":
                note(ctx, "create_overridden", {"cluster": cid, "model": d.reason, "rule": rule.decision})
                d = rule  # never create a complaint for a weak cluster or next to an existing one
            elif d.decision == "CORROBORATE" and (rule.decision != "CORROBORATE" or d.sr_id != rule.sr_id):
                d = rule if rule.decision == "CORROBORATE" else Decision(cluster_id=cid, decision="REVIEW", reason=d.reason)
            elif d.decision == "REPAIR_FAILURE" and rule.decision != "REPAIR_FAILURE":
                d = Decision(cluster_id=cid, decision="REVIEW", reason=d.reason)
            elif d.decision == "REPAIR_FAILURE":
                d.wo_id = rule.wo_id
            hc.decision_reason, hc.agent_run_id = d.reason, ctx.run_id
            if d.decision == "CREATE":
                ctx.call("create_system_complaint", {"cluster_id": cid}, by="apply")
            elif d.decision == "CORROBORATE":
                ctx.call("attach_corroboration", {"sr_id": d.sr_id, "cluster_id": cid}, by="apply")
            elif d.decision == "REPAIR_FAILURE":
                ctx.call("flag_repair_failure", {"wo_id": d.wo_id, "cluster_id": cid}, by="apply")
            elif d.decision == "REVIEW":
                ctx.call("queue_for_review", {"cluster_id": cid, "reason": d.reason}, by="apply")
            else:
                hc.status = "IGNORED"
            final.append(d)
        out.decisions = final


sensing = RoadHazardSensing()


_RUN_LOCK = __import__('threading').Lock()


def run_sensing(force: bool = False) -> int | None:
    from app.agents.runtime.loop import run_agent

    if not _RUN_LOCK.acquire(blocking=False):
        return None  # a run is already in progress (scheduler and demo trigger must not overlap)
    try:
        return run_agent(sensing, "scheduler.sensing" if not force else "demo.run", {"force": force})
    finally:
        _RUN_LOCK.release()
