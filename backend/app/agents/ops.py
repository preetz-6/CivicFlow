"""Agent Operations feed: one timeline of what the agents did, what started each run, and the human decisions.

The point of this view is to show what a normal website cannot: work that nobody clicked. Every agent run carries
its CAUSE (citizen / vehicle feed / clock / another agent / a person / weather), so the UI can draw hand-offs.
"""
from __future__ import annotations

import json
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.router import LABELS
from app.core.actor import Actor
from app.core.db import get_db
from app.core.security import require_roles
from app.models import (
    AgentRun, AgentStep, AuditLog, EventRow, HazardCluster, Incident, ServiceRequest, StatusEvent, User, WeatherAlert,
)
from app.models.enums import Role

router = APIRouter(tags=["agents"])

GUARDRAILS = {
    "p1_capped": "Priority P1 capped to P2: P1 is only for danger to life",
    "fail_downgraded": "FAIL downgraded to FLAG: no hard evidence, a human decides",
    "pass_downgraded": "PASS downgraded to FLAG: a check did not pass",
    "duplicate_rejected": "Claimed duplicate rejected: not within the duplicate radius",
    "create_overridden": "Complaint not created: cluster too weak or a complaint already exists",
    "reassignment_rejected": "Reassignment not proposed: crew unsuitable or busy",
    "ward_mismatch_ignored": "Ward from the model ignored: ward comes from the map boundary",
    "apply_skipped": "No action: an officer had already acted",
}
TOOL_LABELS = {
    "create_system_complaint": "Created a complaint", "attach_corroboration": "Confirmed a citizen complaint",
    "flag_repair_failure": "Flagged a failed repair", "queue_for_review": "Sent to officer review",
    "propose_reassignment": "Proposed a crew reassignment", "raise_material_request": "Raised a material request",
    "send_agency_followup": "Chased the agency", "escalate": "Escalated", "notify_officer": "Informed the officer",
    "notify_citizen": "Informed the citizen",
}
VERBS = {
    ("SR", "SUBMITTED", "ASSIGNED"): "accepted the System Analysis for", ("SR", "SUBMITTED", "REJECTED"): "rejected",
    ("SR", "SUBMITTED", "MERGED"): "merged", ("SR", "MERGED", "SUBMITTED"): "unmerged",
    ("SR", "RESOLVED", "CLOSED"): "confirmed the resolution of", ("SR", "RESOLVED", "REOPENED"): "reopened",
    ("WO", "ASSIGNED", "IN_PROGRESS"): "started", ("WO", "REWORK", "IN_PROGRESS"): "restarted",
    ("WO", "IN_PROGRESS", "COMPLETED"): "marked completed", ("WO", "COMPLETED", "VERIFIED"): "approved",
    ("WO", "COMPLETED", "REWORK"): "sent back for rework",
}


def _short(v, n: int = 140) -> str:
    s = v if isinstance(v, str) else json.dumps(v, ensure_ascii=False, default=str)
    return s if len(s) <= n else s[: n - 1] + "…"


def _step(s: AgentStep) -> dict:
    if s.tool.startswith("action:"):
        name, kind = s.tool[7:], "action"
    elif s.tool.startswith("rule:"):
        name, kind = s.tool[5:], "rule"
    else:
        name, kind = s.tool, "lookup"
    label = TOOL_LABELS.get(name, name.replace("_", " ").capitalize()) if kind == "action" else name.replace("_", " ")
    res = s.result_summary
    if kind == "action" and isinstance(res, dict):
        bits = [f"{k}: {v}" for k, v in res.items() if k in ("sr_id", "new_sr_id", "wo_id", "vehicles", "level",
                                                            "proposal_id", "followups_sent", "sent", "crew_id")]
        summary = ", ".join(bits) or _short(res, 100)
    elif s.error:
        summary = f"error: {_short(s.error, 100)}"
    else:
        summary = _readable(name, res) or _short(res, 140)
    return {"idx": s.idx, "tool": name, "kind": kind, "label": label, "summary": summary}


def _n(x, one: str, many: str | None = None) -> str:
    return f"{x} {one if x == 1 else (many or one + 's')}"


def _readable(tool: str, r) -> str | None:
    """One plain sentence per lookup, for the audience. Falls back to JSON for anything not listed."""
    try:
        if isinstance(r, dict) and r.get("error"):
            return f"not available ({_short(r['error'], 60)})"
        if tool == "get_ward_for_location":
            return f"Ward {r['ward_id']} {r['ward_name']}" if r.get("ward_id") else "outside the wards"
        if tool == "get_sensitive_places_nearby":
            return "; ".join(f"{p['name']} {p['distance_m']} m" for p in r[:3]) if r else "no school, hospital or bus stand nearby"
        if tool == "get_road_class":
            return f"{r['road']} ({r['road_class'].lower()})" if r.get("road") else "local road"
        if tool == "find_nearby_open_complaints":
            if not r:
                return "no similar open complaints nearby"
            return f"{_n(len(r), 'open complaint')} nearby, closest {r[0]['sr_id']} at {r[0]['distance_m']:.0f} m"
        if tool == "get_vehicle_detections_nearby":
            return (f"{_n(r['detections'], 'detection')} from {_n(r['distinct_vehicles'], 'vehicle')}"
                    if r.get("detections") else "no vehicle detections here")
        if tool == "get_planned_works":
            return "; ".join(f"{w['name']} ({w['agency']})" for w in r[:2]) if r else "no planned works nearby"
        if tool == "get_sla_policy":
            return f"{r['priority']} {r['category'].replace('_', ' ').lower()}: resolve within {r['resolution_days']:g} days"
        if tool == "find_nearby_assets":
            return (f"{r[0]['asset_id']} ({r[0]['owner']}) at {r[0]['distance_m']} m" if r else "no asset nearby")
        if tool == "get_asset_history":
            return f"{r['asset_id']}: {_n(r['repairs_in_window'], 'repair')}, {_n(r['complaints_in_window'], 'complaint')} recently"
        if tool == "get_asset_owner":
            return f"maintained by {r['owner']}" + (f" (feeder {r['feeder']})" if r.get("feeder") else "")
        if tool == "get_officer_workload":
            return "; ".join(f"{o['name']}: {o['open_cases']} open" for o in r[:2])
        if tool == "get_recent_repairs":
            return (f"repaired under {r[0]['wo_id']} by {r[0]['crew_id']} {r[0]['verified_days_ago']:g} days ago" if r
                    else "no recent repair here")
        if tool == "check_known_features":
            return f"{r[0]['name']} ({r[0]['distance_m']:.0f} m)" if r else "no speed breaker or rail crossing"
        if tool == "get_work_order":
            return f"{r['wo_id']} for {r['sr_id']} ({r['category'].lower()}), crew {r['crew_id']}, limit {r['allowed_radius_m']} m"
        if tool == "get_photo_metadata":
            if not r.get("has_exif_gps") and not r.get("has_exif_time"):
                return "photo has no GPS or time"
            return f"photo GPS {r['exif_lat']:.5f}, {r['exif_lon']:.5f}" if r.get("has_exif_gps") else "photo has no GPS"
        if tool == "distance_m":
            d = r["distance_m"]
            return f"{d / 1000:.1f} km from the site" if d >= 1000 else f"{d:.0f} m from the site"
        if tool == "compare_with_all_photos":
            return "same as an earlier photo" if r.get("reused") else f"unique among {r['compared']} photos"
        if tool == "get_case_timeline":
            return f"{r['sr_id']} {r['status'].lower().replace('_', ' ')}, SLA {r['sla']['label']}"
        if tool == "get_crew_load":
            return f"crew {r['crew_id']}: {r['open_jobs']}/{r['capacity']} jobs" + (" (overloaded)" if r.get("overloaded") else "")
        if tool == "check_material_stock":
            return f"{r['name']}: {'in stock' if r['in_stock'] else 'out of stock' + (' since ' + r['out_since'] if r.get('out_since') else '')}"
        if tool == "find_available_crews":
            return (f"crew {r[0]['crew_id']} free, {r[0]['distance_km']} km away" if r else "no free crew nearby")
        if tool == "get_referral_status":
            return f"{r['agency']}: {r['agency_status'].lower().replace('_', ' ')}, {_n(r['followups_sent'], 'follow-up')}"
        if tool == "get_cluster_stats":
            return f"{_n(r['distinct_vehicles'], 'vehicle')}, confidence {r['avg_confidence']:.2f}"
        if tool == "get_crew_availability":
            return f"{r['jetting_machines_available']} jetting machines available"
        if tool == "get_weather_alerts":
            return "; ".join(a["title"] for a in r) if r else "no weather alert"
        if tool == "get_recent_complaints":
            return f"{r['total']} flood / drain reports in the last hour"
        if tool == "ward_summary":
            w = r["wards"]
            return f"{len(w)} wards over {r['window_days']} days; most breached: {w[0]['ward_id']} ({w[0]['breached']})" if w else "no data"
        if tool == "list_cases":
            return f"{_n(r['total'], 'matching case')}" + (f", e.g. {', '.join(c['sr_id'] for c in r['cases'][:3])}" if r["cases"] else "")
        if tool == "vehicle_findings":
            return (f"{r['complaints_created_by_vehicles']} complaints filed by vehicles, {r['citizen_complaints_confirmed']} "
                    f"confirmed, {r['failed_repairs_flagged']} failed repairs")
        if tool == "crew_overview":
            over = [c["crew_id"] for c in r["crews"] if c["overloaded"]]
            return f"{_n(len(r['crews']), 'crew')}, overloaded: {', '.join(over) or 'none'}"
        if tool == "search_policies":
            return "; ".join(h["source"] for h in r if h.get("source")) or "nothing relevant"
        if tool == "duplicate_confirmed_by_model":
            return (f"wording alone gave {r['rule_confidence']:.2f}; the agent read both reports and confirmed "
                    f"{r['duplicate_of']} ({r['model_confidence']:.2f})")
        if tool == "triage_tables":
            return f"priority {r['priority']} for {r['department']}" + (f" ({'; '.join(r['bumps'])})" if r.get("bumps") else "")
    except (KeyError, TypeError, IndexError, AttributeError, ValueError):
        return None
    return None


def _cause(db: Session, r: AgentRun) -> dict:
    if r.agent == "sensing":
        ev = db.scalar(select(EventRow).where(EventRow.name == "detections.ingested", EventRow.at <= r.started_at)
                       .order_by(EventRow.id.desc()).limit(1))
        n = (ev.payload or {}).get("accepted") if ev else None
        return {"type": "vehicle_feed", "label": f"Vehicle feed: {n} new detections" if n else "Vehicle feed"}
    if r.agent == "investigator":
        sr = db.get(ServiceRequest, r.subject_id) if r.subject_id else None
        if sr is not None and sr.source == "VEHICLE_FEED":
            hc = db.scalar(select(HazardCluster).where(HazardCluster.sr_id == sr.id).limit(1))
            if hc is not None and hc.agent_run_id:
                return {"type": "agent", "run_id": hc.agent_run_id, "agent": "sensing",
                        "label": f"Road Hazard Sensing created {sr.id} from {hc.distinct_vehicles} vehicles"}
            return {"type": "vehicle_feed", "label": f"Vehicle feed complaint {sr.id}"}
        if r.trigger == "complaint.reopened":
            return {"type": "citizen", "label": f"Citizen reopened {r.subject_id}", "subject_id": r.subject_id}
        return {"type": "citizen", "label": f"Citizen lodged {r.subject_id}", "subject_id": r.subject_id}
    if r.agent == "auditor":
        ev = db.scalar(select(StatusEvent).where(StatusEvent.object_id == r.subject_id, StatusEvent.to_state == "COMPLETED",
                                                 StatusEvent.at <= r.started_at).order_by(StatusEvent.id.desc()).limit(1))
        who = ev.actor_label if ev else "Field team"
        return {"type": "human", "label": f"{who} marked {r.subject_id} completed with an after-photo"}
    if r.agent == "followup":
        sr = (r.input_summary or {}).get("sr_id") or r.subject_id
        return {"type": "clock", "label": {
            "sla.at_risk": f"SLA timer: {sr} reached 75% of its time",
            "sla.breached": f"SLA timer: {sr} passed its deadline",
        }.get(r.trigger, f"Follow-up due: agency has not replied on {sr}")}
    if r.agent == "surge":
        alert = db.scalar(select(WeatherAlert).where(WeatherAlert.issued_at <= r.started_at).order_by(WeatherAlert.id.desc()).limit(1))
        reports = sum(g.get("reports", 0) for g in (r.input_summary or {}).get("candidate_groups", []))
        mode = (r.input_summary or {}).get("mode")
        if mode == "SUMMARY":
            return {"type": "clock", "label": "Hourly situation summary due"}
        lab = f"{reports} flood / drain reports in the last hour"
        return {"type": "weather", "label": f"{alert.title} + {lab}" if alert and alert.active else lab}
    if r.agent == "ask":
        inp = r.input_summary or {}
        return {"type": "human", "label": f"{inp.get('asked_by', 'Staff')} asked: {_short(inp.get('question', ''), 90)}"}
    return {"type": "clock", "label": r.trigger}


def _run_item(db: Session, r: AgentRun, users: dict[int, str]) -> dict:
    steps = db.scalars(select(AgentStep).where(AgentStep.run_id == r.id).order_by(AgentStep.idx)).all()
    guard = [GUARDRAILS[s.tool[5:]] for s in steps if s.tool.startswith("rule:") and s.tool[5:] in GUARDRAILS]
    return {
        "kind": "agent_run", "key": f"run-{r.id}", "at": r.started_at, "id": r.id, "agent": r.agent,
        "agent_label": LABELS.get(r.agent, r.agent), "status": r.status, "model": r.model, "trigger": r.trigger,
        "cause": _cause(db, r), "subject_type": r.subject_type, "subject_id": r.subject_id, "decision": r.decision,
        "confidence": r.confidence, "latency_ms": r.latency_ms, "steps": [_step(s) for s in steps],
        "guardrails": list(dict.fromkeys(guard)),
        "human": {"accepted_by": users.get(r.accepted_by), "overridden_by": users.get(r.overridden_by),
                  "override_reason": r.override_reason},
    }


@router.get("/agent-ops/feed")
def feed(limit: int = Query(80, ge=1, le=300), db: Session = Depends(get_db),
         actor: Actor = Depends(require_roles(Role.CONTROL_ROOM))):
    users = dict(db.execute(select(User.id, User.name)).all())
    roles = dict(db.execute(select(User.name, User.role)).all())
    items: list[dict] = []

    runs = db.scalars(select(AgentRun).where(AgentRun.trigger != "seed.backfill").order_by(AgentRun.id.desc()).limit(limit))
    items += [_run_item(db, r, users) for r in runs]

    for e in db.scalars(select(StatusEvent).where(StatusEvent.actor_type == "HUMAN", StatusEvent.actor.notlike("seed:%"))
                        .order_by(StatusEvent.id.desc()).limit(limit)):
        if e.from_state is None:
            continue  # creations are listed below from the complaint itself
        verb = VERBS.get((e.object_type, e.from_state, e.to_state), f"moved {e.from_state} → {e.to_state} on")
        who = e.actor_label or e.actor
        if e.actor.startswith("citizen:") or who.startswith("Citizen"):
            items.append({"kind": "citizen", "key": f"se-{e.id}", "at": e.at, "subject_id": e.object_id,
                          "text": f"Citizen {verb} {e.object_id}"})
            continue
        name = who.split(" (")[0]
        items.append({"kind": "human", "key": f"se-{e.id}", "at": e.at, "actor": name, "role": roles.get(name, ""),
                      "text": f"{name} {verb} {e.object_id}" + (f": {e.reason}" if e.reason and "Accepted" not in e.reason else ""),
                      "subject_id": e.object_id})

    # complaints lodged by citizens (vehicle-feed complaints appear as agent actions instead)
    for e in db.scalars(select(StatusEvent).where(StatusEvent.object_type == "SR", StatusEvent.from_state.is_(None),
                                                  StatusEvent.actor.notlike("seed:%"), StatusEvent.actor.notlike("agent:%"))
                        .order_by(StatusEvent.id.desc()).limit(limit)):
        sr = db.get(ServiceRequest, e.object_id)
        if sr is None or sr.source == "VEHICLE_FEED":
            continue
        items.append({"kind": "citizen", "key": f"se-{e.id}", "at": e.at, "subject_id": sr.id,
                      "text": f"Citizen lodged {sr.id}: {sr.category.replace('_', ' ').lower()} in {sr.ward_id or 'the city'}"})

    for a in db.scalars(select(AuditLog).where(AuditLog.action.in_(["WO.reassign", "incident.publish_advisory", "SR.override"]))
                        .order_by(AuditLog.id.desc()).limit(limit)):
        uid = int(a.actor.split(":")[1]) if a.actor.startswith("user:") else None
        name = users.get(uid, a.actor)
        obj = a.object.split(":", 1)[-1]
        text = {"WO.reassign": f"{name} approved the reassignment of {obj} to crew {(a.after_json or {}).get('crew_id')}",
                "incident.publish_advisory": f"{name} published the public advisory for incident {obj}",
                "SR.override": f"{name} overrode the System Analysis for {obj}: {(a.after_json or {}).get('reason', '')}"}[a.action]
        items.append({"kind": "human", "key": f"audit-{a.id}", "at": a.at, "actor": name, "role": roles.get(name, ""),
                      "text": text, "subject_id": obj})

    for ev in db.scalars(select(EventRow).where(EventRow.name == "detections.ingested").order_by(EventRow.id.desc()).limit(20)):
        p = ev.payload or {}
        items.append({"kind": "feed", "key": f"ev-{ev.id}", "at": ev.at, "source": p.get("source", "vehicle feed"),
                      "text": f"Vehicle feed: {p.get('accepted', '?')} road-hazard detections received"})

    items.sort(key=lambda i: (i["at"] or datetime.min, i["key"]), reverse=True)
    return items[:limit]


@router.get("/agent-ops/summary")
def summary(hours: float | None = Query(None, gt=0, description="only the last N hours (server clock); omit for all time"),
            db: Session = Depends(get_db), actor: Actor = Depends(require_roles(Role.CONTROL_ROOM))):
    """Counters for the top of the page. 'autonomous' = runs that no person started (vehicle feed, clock, another
    agent, weather): the part a normal website cannot do."""
    from datetime import timedelta

    from app.core.clock import now

    since = now() - timedelta(hours=hours) if hours else None
    q = select(AgentRun).where(AgentRun.trigger != "seed.backfill")
    if since:
        q = q.where(AgentRun.started_at >= since)
    runs = db.scalars(q).all()
    by_agent: dict[str, int] = {}
    autonomous = 0
    for r in runs:
        lab = LABELS.get(r.agent, r.agent)
        by_agent[lab] = by_agent.get(lab, 0) + 1
        if _cause(db, r)["type"] not in ("citizen", "human"):
            autonomous += 1
    run_ids = [r.id for r in runs]
    n_actions = len(db.scalars(select(AgentStep.id).where(AgentStep.tool.like("action:%"), AgentStep.run_id.in_(run_ids))).all()) if run_ids else 0
    hq = select(StatusEvent.id).where(StatusEvent.actor_type == "HUMAN", StatusEvent.from_state.is_not(None),
                                      StatusEvent.actor.like("user:%"))
    iq = select(Incident.id)
    if since:
        hq, iq = hq.where(StatusEvent.at >= since), iq.where(Incident.created_at >= since)
    return {"runs": len(runs), "by_agent": by_agent, "autonomous_runs": autonomous, "actions": n_actions,
            "human_decisions": len(db.scalars(hq).all()), "incidents": len(db.scalars(iq).all()),
            "window_hours": hours}
