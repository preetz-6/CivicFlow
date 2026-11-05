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
        summary = _short(res, 140)
    return {"idx": s.idx, "tool": name, "kind": kind, "label": label, "summary": summary}


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

    for e in db.scalars(select(StatusEvent).where(StatusEvent.actor_type == "HUMAN").order_by(StatusEvent.id.desc()).limit(limit)):
        if e.from_state is None:  # creation = a citizen report
            items.append({"kind": "citizen", "key": f"se-{e.id}", "at": e.at, "subject_id": e.object_id,
                          "text": f"Citizen lodged {e.object_id}"})
            continue
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
def summary(db: Session = Depends(get_db), actor: Actor = Depends(require_roles(Role.CONTROL_ROOM))):
    """Counters for the top of the page. 'autonomous' = runs that no person started (vehicle feed, clock, another
    agent, weather): the part a normal website cannot do."""
    runs = db.scalars(select(AgentRun).where(AgentRun.trigger != "seed.backfill")).all()
    by_agent: dict[str, int] = {}
    autonomous = 0
    for r in runs:
        lab = LABELS.get(r.agent, r.agent)
        by_agent[lab] = by_agent.get(lab, 0) + 1
        if _cause(db, r)["type"] not in ("citizen", "human"):
            autonomous += 1
    n_actions = len(db.scalars(select(AgentStep.id).where(AgentStep.tool.like("action:%"))).all())
    humans = len(db.scalars(select(StatusEvent.id).where(StatusEvent.actor_type == "HUMAN", StatusEvent.from_state.is_not(None),
                                                         StatusEvent.actor.like("user:%"))).all())
    return {"runs": len(runs), "by_agent": by_agent, "autonomous_runs": autonomous, "actions": n_actions,
            "human_decisions": humans, "incidents": len(db.scalars(select(Incident.id)).all())}
