"""Agent 5: Surge Commander (kept small; reuses the PostGIS DBSCAN approach of Agent 3).

Trigger (deterministic check every ~20 s): >= 15 flood/drain/tree-fall complaints in the last 60 SLA-minutes
in one area, OR an active weather alert plus >= 6 such complaints. Groups them into incidents, suggests crews
as TEXT, drafts a public advisory (a human publishes it to the ticker) and a situation summary for the
Commissioner, refreshed every simulated hour. New complaints near an active incident are linked automatically.
"""
from __future__ import annotations

import math
from datetime import timedelta
from typing import Literal

from pydantic import BaseModel, Field
from sqlalchemy import select, text

from app.agents.runtime.base import Agent
from app.agents.runtime.tools import note, props, tool
from app.core.clock import IST, now
from app.models import Crew, Incident, Inventory, ServiceRequest, SystemState, Timeline, WeatherAlert
from app.modules import geo
from app.modules.notifications.service import notify_citizen
from app.seed.geo import demo_points

SURGE_CATS = ("WATERLOGGING", "DRAIN_BLOCKED", "TREE_FALL")
WINDOW_MIN = 60
SURGE_N = 15
SURGE_N_WITH_ALERT = 6
GROUP_EPS_M = 1000
LINK_RADIUS_M = 1200
SUMMARY_EVERY_H = 1

GROUP_SQL = text("""
SELECT cid, array_agg(id ORDER BY created_at) AS ids, count(*) AS n,
       ST_Y(ST_Centroid(ST_Collect(location))) AS lat, ST_X(ST_Centroid(ST_Collect(location))) AS lon,
       mode() WITHIN GROUP (ORDER BY category) AS category
FROM (SELECT id, location, category, created_at,
             ST_ClusterDBSCAN(ST_Transform(location, 32643), eps := :eps, minpoints := 3) OVER () AS cid
      FROM service_requests
      WHERE category = ANY(:cats) AND created_at >= :since AND incident_id IS NULL
        AND status NOT IN ('CLOSED', 'REJECTED', 'MERGED')) s
WHERE cid IS NOT NULL GROUP BY cid ORDER BY n DESC
""")


def recent_unlinked(db) -> list[ServiceRequest]:
    return list(db.scalars(select(ServiceRequest).where(
        ServiceRequest.category.in_(SURGE_CATS), ServiceRequest.created_at >= now() - timedelta(minutes=WINDOW_MIN),
        ServiceRequest.incident_id.is_(None), ServiceRequest.status.notin_(["CLOSED", "REJECTED", "MERGED"]))))


def active_alerts(db) -> list[WeatherAlert]:
    return list(db.scalars(select(WeatherAlert).where(WeatherAlert.active.is_(True)).where(
        (WeatherAlert.expires_at.is_(None)) | (WeatherAlert.expires_at > now()))))


def area_name(db, lat: float, lon: float) -> str:
    best, bd = None, 1e9
    for a in demo_points()["rain_areas"]:
        d = geo.distance_m((lat, lon), (a["lat"], a["lon"]))
        if d < bd:
            best, bd = a["name"], d
    if best and bd <= 1200:
        return best
    w = geo.ward_for(db, lat, lon)
    return w.name if w else "City"


def groups(db, eps: float = GROUP_EPS_M) -> list[dict]:
    rows = db.execute(GROUP_SQL, {"eps": eps, "cats": list(SURGE_CATS),
                                  "since": now() - timedelta(minutes=WINDOW_MIN)}).all()
    return [{"group_key": f"G{i + 1}", "sr_ids": list(r.ids), "reports": r.n, "lat": round(r.lat, 6),
             "lon": round(r.lon, 6), "main_category": r.category, "area_hint": area_name(db, r.lat, r.lon)}
            for i, r in enumerate(rows)]


def link(db, sr: ServiceRequest, inc: Incident, actor_type: str = "AGENT") -> None:
    if sr.incident_id:
        return
    sr.incident_id = inc.id
    inc.report_count = (inc.report_count or 0) + 1
    db.add(Timeline(sr_id=sr.id, stage="Part of Active Incident",
                    remarks=f"Your grievance is part of an active incident ({inc.name}) being handled by our crews.",
                    remarks_kn=f"ನಿಮ್ಮ ದೂರು ಸಕ್ರಿಯ ಘಟನೆಯ ({inc.name}) ಭಾಗವಾಗಿದ್ದು, ನಮ್ಮ ತಂಡಗಳು ಕಾರ್ಯನಿರ್ವಹಿಸುತ್ತಿವೆ.",
                    actor_type=actor_type, at=now()))
    notify_citizen(db, sr, "INCIDENT", {"incident": inc.name}, dedupe=str(inc.id))


# ----------------------------------------------------------------------------- tools
@tool("get_recent_complaints", "Recent complaints of given categories (default flood/drain/tree-fall) in the last N minutes.",
      {"properties": props(categories={"type": "array", "items": {"type": "string"}}, minutes=("integer", "default 60"))})
def get_recent_complaints(ctx, categories: list[str] | None = None, minutes: int = WINDOW_MIN):
    q = select(ServiceRequest).where(ServiceRequest.category.in_(categories or SURGE_CATS),
                                     ServiceRequest.created_at >= now() - timedelta(minutes=minutes))
    rows = ctx.db.scalars(q.order_by(ServiceRequest.created_at)).all()
    by_cat: dict[str, int] = {}
    for r in rows:
        by_cat[r.category] = by_cat.get(r.category, 0) + 1
    return {"total": len(rows), "by_category": by_cat, "linked_to_incident": sum(r.incident_id is not None for r in rows)}


@tool("cluster_complaints", "Group recent unlinked flood/drain/tree-fall complaints by area (DBSCAN).",
      {"properties": props(eps_m=("number", "grouping distance in metres, default 1000"))})
def cluster_complaints(ctx, eps_m: float = GROUP_EPS_M):
    return [{k: v for k, v in g.items() if k != "sr_ids"} for g in groups(ctx.db, eps_m)]


@tool("get_weather_alerts", "Active weather alerts (SIMULATED weather adapter).", {"properties": {}})
def get_weather_alerts(ctx):
    return [{"title": a.title, "severity": a.severity, "area": a.area_name,
             "issued": a.issued_at.astimezone(IST).strftime("%d %b %H:%M")} for a in active_alerts(ctx.db)]


@tool("get_crew_availability", "Drain/flood-capable crews and jetting machines available.",
      {"properties": props(zone=("string", "default West Zone"))})
def get_crew_availability(ctx, zone: str = "West Zone"):
    from app.agents.followup import crew_load

    crews = [{"crew_id": c.id, "ward_id": c.ward_id, "open_jobs": crew_load(ctx.db, c.id), "capacity": c.capacity}
             for c in ctx.db.scalars(select(Crew)) if "DRAINS" in (c.skills or [])]
    jet = ctx.db.get(Inventory, "jetting_machine")
    return {"drain_crews": crews, "jetting_machines_available": int(jet.qty) if jet else 0}


# ----------------------------------------------------------------------------- agent
class IncidentPlan(BaseModel):
    group_key: str
    name: str = Field(description='e.g. "Kengeri Underpass Waterlogging"')
    severity: Literal["MEDIUM", "HIGH", "SEVERE"]
    crew_suggestion: str = Field(description='Text only, e.g. "2 jetting machines + 1 desilting crew"')


class SurgePlan(BaseModel):
    mode: Literal["NEW_INCIDENTS", "SUMMARY"]
    incidents: list[IncidentPlan] = []
    advisory_draft: str | None = Field(None, description="Public advisory for the website ticker / SMS, under 160 characters")
    advisory_draft_kn: str | None = None
    situation_summary: str = Field(description="3-5 sentences for the Commissioner")
    confidence: float = Field(ge=0, le=1)


SYSTEM = """You are the Surge Commander for CivicFlow Municipal Corporation. During heavy rain, dozens of
waterlogging / drain / tree-fall complaints arrive at once. Turn them into a few manageable incidents.
mode NEW_INCIDENTS: for each candidate group give a short place-based name ("Kengeri Underpass Waterlogging",
"RR Nagar Arch Drain Overflow"), a severity (SEVERE >= 15 reports, HIGH >= 8, else MEDIUM; raise if near a hospital,
school or underpass) and a crew suggestion AS TEXT based on get_crew_availability (never more jetting machines than
are available). Draft ONE public advisory (plain, calm, under 160 characters, e.g. "Avoid Kengeri underpass; crews
deployed.") and a Kannada version if you can.
mode SUMMARY: only refresh situation_summary for the active incidents.
situation_summary (for the Commissioner): incidents, report counts, weather, crews suggested, what is pending."""


class SurgeCommander(Agent):
    name = "surge"
    label = "Surge Commander"
    system_prompt = SYSTEM
    triggers: list[str] = []
    output_model = SurgePlan
    subject_type = "INCIDENT"
    max_steps = 8
    timeout_s = 60.0
    tools = ["get_recent_complaints", "cluster_complaints", "get_weather_alerts", "get_crew_availability",
             "get_sensitive_places_nearby"]

    def build_input(self, db, payload):
        # 1. new complaints near an ACTIVE incident join it (deterministic; no agent needed)
        active = list(db.scalars(select(Incident).where(Incident.status == "ACTIVE")))
        for sr in recent_unlinked(db):
            lat, lon = geo.latlon(sr.location)
            near = [(geo.distance_m((lat, lon), geo.latlon(i.center)), i) for i in active]
            near = [x for x in near if x[0] <= LINK_RADIUS_M]
            if near:
                link(db, sr, min(near, key=lambda x: x[0])[1], "SYSTEM")
        db.flush()
        # 2. surge trigger
        alerts = active_alerts(db)
        gs = groups(db)
        total = sum(g["reports"] for g in gs)
        big = any(g["reports"] >= SURGE_N for g in gs)
        if gs and (big or payload.get("force") or (alerts and total >= SURGE_N_WITH_ALERT)):
            return {"subject_id": f"{len(gs)} groups / {total} reports", "mode": "NEW_INCIDENTS", "candidate_groups": gs,
                    "weather_alerts": [a.title for a in alerts], "trigger": "surge" if big else "weather alert + rising reports",
                    "active_incidents": [{"id": i.id, "name": i.name, "reports": i.report_count} for i in active]}
        # 3. hourly situation summary
        if active:
            last = max((i.summary_at for i in active if i.summary_at), default=None)
            if last is None or now() - last >= timedelta(hours=SUMMARY_EVERY_H):
                return {"subject_id": f"{len(active)} active incidents", "mode": "SUMMARY",
                        "weather_alerts": [a.title for a in alerts],
                        "active_incidents": [{"id": i.id, "name": i.name, "reports": i.report_count, "severity": i.severity,
                                              "crew_suggestion": i.crew_suggestion} for i in active]}
        return None

    def render_input(self, inp):
        import json

        body = {k: v for k, v in inp.items() if not k.startswith("_")}
        body["candidate_groups"] = [{**g, "sr_ids": g["sr_ids"][:5]} for g in body.get("candidate_groups", [])]
        return f"mode: {inp['mode']}\nInput:\n" + json.dumps(body, default=str, indent=1)

    def decision(self, out: SurgePlan) -> str:
        if out.mode == "SUMMARY":
            return "situation summary refreshed"
        return f"{len(out.incidents)} incident(s): " + "; ".join(f"{i.name} ({i.severity})" for i in out.incidents)

    def rationale(self, out: SurgePlan) -> str:
        return out.situation_summary

    def fallback(self, ctx, inp):
        avail = ctx.call("get_crew_availability", {}, by="rules")
        alerts = ctx.call("get_weather_alerts", {}, by="rules")
        jets = max(avail["jetting_machines_available"], 0)
        plans = []
        if inp["mode"] == "NEW_INCIDENTS":
            ctx.call("get_recent_complaints", {}, by="rules")
            for g in inp["candidate_groups"]:
                n = min(max(1, math.ceil(g["reports"] / 8)), max(jets, 1))
                jets = max(jets - n, 0)
                kind = {"DRAIN_BLOCKED": "Drain Overflow", "TREE_FALL": "Tree Fall"}.get(g["main_category"], "Waterlogging")
                sev = "SEVERE" if g["reports"] >= 15 else "HIGH" if g["reports"] >= 8 else "MEDIUM"
                plans.append(IncidentPlan(group_key=g["group_key"], name=f"{g['area_hint']} {kind}", severity=sev,
                                          crew_suggestion=f"{n} jetting machine{'s' if n > 1 else ''} + 1 desilting crew"))
        areas = " and ".join(dict.fromkeys(g["area_hint"] for g in inp.get("candidate_groups", []))) if plans else None
        adv = f"Avoid {areas}: waterlogging reported, crews deployed. Please use alternate routes." if areas else None
        adv_kn = f"{areas} ಪ್ರದೇಶವನ್ನು ತಪ್ಪಿಸಿ: ನೀರು ನಿಂತಿದೆ, ತಂಡಗಳನ್ನು ನಿಯೋಜಿಸಲಾಗಿದೆ. ಪರ್ಯಾಯ ಮಾರ್ಗ ಬಳಸಿ." if areas else None
        return SurgePlan(mode=inp["mode"], incidents=plans, advisory_draft=adv, advisory_draft_kn=adv_kn,
                         situation_summary=self._summary(inp, plans, alerts, avail), confidence=0.8)

    @staticmethod
    def _summary(inp, plans, alerts, avail) -> str:
        parts = [f"As of {now().astimezone(IST):%d %b %H:%M} IST:"]
        if plans:
            gs = {g["group_key"]: g for g in inp["candidate_groups"]}
            parts.append(f"{len(plans)} new incident(s): " + "; ".join(
                f"{p.name} ({gs[p.group_key]['reports']} reports, {p.severity}; suggested {p.crew_suggestion})" for p in plans) + ".")
        for i in inp.get("active_incidents", []):
            parts.append(f"{i['name']}: {i['reports']} reports.")
        parts.append(("Weather: " + "; ".join(a["title"] for a in alerts) + ".") if alerts else "No active weather alert.")
        parts.append(f"{avail['jetting_machines_available']} jetting machine(s) in stores; actual deployment needs Control Room approval.")
        return " ".join(parts)

    def apply(self, ctx, inp, out: SurgePlan):
        db = ctx.db
        if out.mode == "NEW_INCIDENTS" and inp["mode"] == "NEW_INCIDENTS":
            gs = {g["group_key"]: g for g in inp["candidate_groups"]}
            for p in out.incidents:
                g = gs.get(p.group_key)
                if g is None:
                    continue
                srs = [s for s in (db.get(ServiceRequest, i) for i in g["sr_ids"]) if s and s.incident_id is None]
                if len(srs) < 3:
                    continue
                inc = Incident(name=p.name[:120], category=g["main_category"], center=geo.make_point(g["lat"], g["lon"]),
                               severity=p.severity, status="ACTIVE", report_count=0, crew_suggestion=p.crew_suggestion,
                               advisory_draft=out.advisory_draft, advisory_draft_kn=out.advisory_draft_kn,
                               summary=out.situation_summary, summary_at=now(), agent_run_id=ctx.run_id, created_at=now())
                db.add(inc)
                db.flush()
                for s in srs:
                    link(db, s, inc)
                note(ctx, "incident_created", {"incident_id": inc.id, "name": inc.name, "reports": inc.report_count})
        for inc in db.scalars(select(Incident).where(Incident.status == "ACTIVE")):
            inc.summary, inc.summary_at = out.situation_summary, now()
        db.merge(SystemState(key="surge_last", value={"at": now().isoformat()}))


surge = SurgeCommander()


_RUN_LOCK = __import__('threading').Lock()


def run_surge_check(force: bool = False) -> int | None:
    from app.agents.runtime.loop import run_agent

    if not _RUN_LOCK.acquire(blocking=False):
        return None  # a run is already in progress (scheduler and demo trigger must not overlap)
    try:
        return run_agent(surge, "demo.run" if force else "scheduler.surge_check", {"force": force})
    finally:
        _RUN_LOCK.release()


def display_name(inc: Incident) -> str:
    return f"{inc.name} — {inc.report_count} reports"
