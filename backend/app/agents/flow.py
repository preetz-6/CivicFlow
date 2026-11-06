"""Public "How the agents work" view: one case as a simple chain of boxes, in time order.

Reuses the Agent Operations helpers (cause, plain-language steps, guardrails). Public, so it carries no names,
phone numbers or complaint text: people are shown by their role only.
"""
from __future__ import annotations

import re
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.ops import GUARDRAILS, _cause, _short, _step
from app.agents.router import LABELS
from app.agents.runtime.tools import REGISTRY
from app.core.db import get_db
from app.models import AgentRun, AgentStep, HazardCluster, ServiceRequest, StatusEvent, User, WorkOrder

router = APIRouter(tags=["public"])

ROLE_LABELS = {"WARD_OFFICER": "Ward Officer", "FIELD_TEAM": "Field crew", "CONTROL_ROOM": "Control Room",
               "CITIZEN": "Citizen"}
PERSON_VERBS = {
    ("SR", "SUBMITTED", "ASSIGNED"): "Accepted the agent's analysis",
    ("SR", "SUBMITTED", "REJECTED"): "Rejected the complaint",
    ("SR", "MERGED", "SUBMITTED"): "Un-merged the complaint",
    ("SR", "RESOLVED", "CLOSED"): "Confirmed it is fixed",
    ("SR", "RESOLVED", "REOPENED"): "Reopened: not fixed",
    ("WO", "ASSIGNED", "IN_PROGRESS"): "Started the work",
    ("WO", "REWORK", "IN_PROGRESS"): "Restarted the work",
    ("WO", "IN_PROGRESS", "COMPLETED"): "Finished and uploaded a photo",
    ("WO", "COMPLETED", "VERIFIED"): "Gave final approval",
    ("WO", "COMPLETED", "REWORK"): "Sent back for rework",
}


def _sr_of_run(db: Session, r: AgentRun) -> str | None:
    if r.subject_type == "SR":
        return r.subject_id
    if r.subject_type == "WO" and r.subject_id:
        wo = db.get(WorkOrder, r.subject_id)
        return wo.sr_id if wo else None
    return (r.input_summary or {}).get("sr_id")


def _how(model: str | None) -> str:
    if not model or model == "rules":
        return "Rule-based (same tools and checks, no AI model)"
    if model.startswith("replay:"):
        return f"AI model {model[7:]} (recorded run)"
    return f"AI model {model}"


KEEP_UPPER = {"BESCOM", "BWSSB", "SLA", "GPS", "EXIF", "FAIL", "PASS", "FLAG"}


def _plain(text: str | None) -> str:
    """'AT_RISK: CREW_OVERLOAD -> propose W13-B' -> 'At risk: crew overload → propose W13-B'."""
    if not text:
        return ""
    t = re.sub(r"\b[A-Z][A-Z_]{2,}\b", lambda m: m.group() if m.group() in KEEP_UPPER else m.group().replace("_", " ").lower(), text)
    t = t.replace("->", "→").replace("+", " + ").replace("_", " ")
    return t[:1].upper() + t[1:]


def _plain_step(s: AgentStep) -> dict:
    """Rule-based runs log their lookups as 'rule:<tool>'; show those as lookups, like the AI-model runs."""
    st = _step(s)
    name = st["tool"]
    if name == "citizen_notified":
        msg = (s.result_summary or {}).get("message") if isinstance(s.result_summary, dict) else None
        return {"kind": "action", "label": "Texted the citizen", "summary": f"“{_short(msg, 160)}”" if msg else "sent"}
    if name == "triage_tables":
        return {"kind": "rule", "label": "Priority rules", "summary": st["summary"]}
    if st["kind"] == "rule" and name in REGISTRY:
        st["kind"] = "lookup"
    if st["kind"] == "lookup":
        st["label"] = re.sub(r"^(get|find|check|compare with) ", "", name.replace("_", " "))
        st["label"] = {"search policies": "the Citizen Charter and rules", "list cases": "matching cases",
                       "crew overview": "all crews", "vehicle findings": "vehicle feed findings"}.get(st["label"], st["label"])
    if st["summary"] in ("sent: True", "sent: true"):
        st["summary"] = "done"
    if isinstance(s.result_summary, dict) and s.result_summary.get("material_request_id"):
        st["summary"] = f"request no. {s.result_summary['material_request_id']}"
    return {"kind": st["kind"], "label": st["label"], "summary": st["summary"]}


def _agent_box(db: Session, r: AgentRun) -> dict:
    steps = db.scalars(select(AgentStep).where(AgentStep.run_id == r.id).order_by(AgentStep.idx)).all()
    is_guard = [s.tool.startswith("rule:") and s.tool[5:] in GUARDRAILS for s in steps]
    guard = list(dict.fromkeys(GUARDRAILS[s.tool[5:]] for s, g in zip(steps, is_guard) if g))
    shown = [_plain_step(s) for s, g in zip(steps, is_guard) if not g]
    result = _plain(r.decision)
    if r.confidence is not None:
        result += f" (confidence {r.confidence:.2f})"
    return {
        "key": f"run-{r.id}", "kind": "agent", "at": r.started_at, "title": LABELS.get(r.agent, r.agent),
        "line": _short(_plain(r.decision) or ("Working…" if r.status == "RUNNING" else ""), 70),
        "running": r.status == "RUNNING", "sent_back": (r.output or {}).get("verdict") == "FAIL",
        "detail": {
            "started_by": _cause(db, r)["label"], "how": _how(r.model),
            "steps": [{"n": i + 1, **s} for i, s in enumerate(shown)],
            "reasoning": [ln.strip().lstrip("-").strip() for ln in (r.rationale or "").splitlines() if ln.strip()],
            "guardrails": guard, "result": result.strip(),
        },
    }


def _person_box(key: str, at, who: str, what: str, result: str | None = None) -> dict:
    return {"key": key, "kind": "person", "at": at, "title": who, "line": what,
            "detail": {"started_by": None, "how": None, "steps": [], "reasoning": [], "guardrails": [],
                       "result": result or what}}


def _event_sr(db: Session, e: StatusEvent) -> str | None:
    if e.object_type == "SR":
        return e.object_id
    wo = db.get(WorkOrder, e.object_id)
    return wo.sr_id if wo else None


def _latest_sr(db: Session) -> str | None:
    """The case touched most recently by an agent or a person (seed history ignored)."""
    best: tuple[datetime, str] | None = None
    for r in db.scalars(select(AgentRun).where(AgentRun.trigger != "seed.backfill").order_by(AgentRun.id.desc()).limit(20)):
        sr = _sr_of_run(db, r)
        if sr:
            best = (r.started_at, sr)
            break
    e = db.scalar(select(StatusEvent).where(StatusEvent.actor.notlike("seed:%")).order_by(StatusEvent.id.desc()).limit(1))
    if e is not None:
        sr = _event_sr(db, e)
        if sr and (best is None or e.at > best[0]):
            best = (e.at, sr)
    return best[1] if best else None


def _recent_cases(db: Session, n: int = 6) -> list[str]:
    out: list[str] = []
    for r in db.scalars(select(AgentRun).where(AgentRun.trigger != "seed.backfill").order_by(AgentRun.id.desc()).limit(80)):
        sr = _sr_of_run(db, r)
        if sr and sr not in out:
            out.append(sr)
        if len(out) >= n:
            break
    return out


@router.get("/public/agent-flow")
def agent_flow(sr: str | None = Query(None, max_length=24), db: Session = Depends(get_db)):
    """One case as a chain of boxes. With no `sr`: the case touched most recently (for "follow live")."""
    recent = _recent_cases(db)
    sr_id = (sr or "").strip().upper() or _latest_sr(db)
    case = db.get(ServiceRequest, sr_id) if sr_id else None
    if case is None:
        return {"sr_id": sr_id, "found": False, "recent": recent, "boxes": []}
    ids = [case.id, *db.scalars(select(WorkOrder.id).where(WorkOrder.sr_id == case.id))]
    roles = {f"user:{uid}": role for uid, role in db.execute(select(User.id, User.role)).all()}

    # how the case started: always first
    start: list[dict] = []
    if case.source == "VEHICLE_FEED":
        hc = db.scalar(select(HazardCluster).where(HazardCluster.sr_id == case.id).limit(1))
        srun = db.get(AgentRun, hc.agent_run_id) if hc is not None and hc.agent_run_id else None
        start.append({"key": "start", "kind": "trigger", "at": srun.started_at if srun else case.created_at,
                      "title": "Vehicle feed", "line": "Bumps reported by connected vehicles"})
        if srun is not None:
            start.append(_agent_box(db, srun))
    else:
        cat = case.category.replace("_", " ").lower()
        start.append(_person_box("start", case.created_at, "Citizen", f"Reported a {cat} in {case.ward_id or 'the city'}",
                                 f"Grievance {case.id} registered (no login needed)"))

    rest: list[dict] = []
    runs = list(db.scalars(select(AgentRun).where(AgentRun.trigger != "seed.backfill", AgentRun.agent.notin_(["sensing", "ask"]),
                                                  AgentRun.subject_id.in_(ids))))
    runs += [r for r in db.scalars(select(AgentRun).where(AgentRun.agent == "followup").order_by(AgentRun.id.desc()).limit(500))
             if (r.input_summary or {}).get("sr_id") == case.id and r.subject_id not in ids]
    for r in runs:
        cause = _cause(db, r)
        if cause["type"] in ("clock", "weather"):  # nobody clicked: show what woke the agent up
            rest.append({"key": f"why-{r.id}", "kind": "trigger", "at": r.started_at,
                         "title": "Timer" if cause["type"] == "clock" else "Weather", "line": _short(cause["label"], 70)})
        rest.append(_agent_box(db, r))

    for e in db.scalars(select(StatusEvent).where(StatusEvent.object_id.in_(ids), StatusEvent.actor_type == "HUMAN",
                                                  StatusEvent.from_state.is_not(None), StatusEvent.actor.notlike("seed:%"))):
        who = ROLE_LABELS.get(roles.get(e.actor, ""), "Citizen" if e.actor.startswith("citizen") else "Staff")
        what = PERSON_VERBS.get((e.object_type, e.from_state, e.to_state),
                                f"Moved {e.from_state.replace('_', ' ').lower()} to {e.to_state.replace('_', ' ').lower()}")
        why = f"{what}: {_short(e.reason, 120)}" if e.reason and e.to_state in ("REWORK", "REJECTED", "REOPENED") else None
        rest.append(_person_box(f"se-{e.id}", e.at, who, what, why))

    rest.sort(key=lambda b: (b["at"] or datetime.min, 0 if b["kind"] == "trigger" else 1, b["key"]))
    return {"sr_id": case.id, "found": True, "recent": recent,
            "title": f"{case.category.replace('_', ' ').capitalize()} in {case.ward_id or 'the city'}",
            "status": case.status.replace("_", " ").lower(), "boxes": start + rest}


@router.get("/public/agent-activity")
def agent_activity(limit: int = Query(6, ge=1, le=20), db: Session = Depends(get_db)):
    """Public. Recent agent actions for the home page "Live now" strip and the staff pop-up notices.
    Decisions only (category, ward, priority): no names, phones or complaint text."""
    from datetime import timedelta

    from app.core.clock import clock, now

    # the app clock can run faster than real time (TIME_SCALE): "last hour" and "ago" are in real time
    scale = max(clock.scale, 1e-9)
    t = now()
    base = select(AgentRun).where(AgentRun.trigger != "seed.backfill", AgentRun.status != "RUNNING", AgentRun.agent != "ask")
    hour = len(db.scalars(base.where(AgentRun.started_at >= t - timedelta(hours=scale))).all())
    latest = [{"id": r.id, "agent": r.agent, "agent_label": LABELS.get(r.agent, r.agent), "subject_id": r.subject_id,
               "text": _short(_plain(r.decision) or "checked the case", 90), "at": r.started_at,
               "ago_s": max(0, int((t - r.started_at).total_seconds() / scale)),
               "autonomous": _cause(db, r)["type"] not in ("citizen", "human")}
              for r in db.scalars(base.order_by(AgentRun.id.desc()).limit(limit))]
    return {"last_hour": hour, "latest": latest}
