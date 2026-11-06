"""Agent 6: Ask CivicFlow (on demand, for the Commissioner and officers).

A question in plain English ("Which ward is worst this week and why?", "Why is SR-2026-001257 late?") is answered
by an agent that chooses its own lookups over the LIVE database, plus a small search over the Citizen Charter and
the service rules (retrieval). Every lookup is logged like any other agent step, and every number in the answer
comes from a tool result. Read-only: this agent never changes a case.

Without a model (no key, quota used up) a rule-based version routes the question to the same tools by keywords.
"""
from __future__ import annotations

import re
from collections import Counter, defaultdict
from datetime import timedelta

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.runtime.base import Agent
from app.agents.runtime.tools import ToolContext, props, tool
from app.core.clock import now
from app.core.db import get_db
from app.core.security import require_roles
from app.domain_config import (
    AGENCY_ESCALATE_AFTER_FOLLOWUPS, AGENCY_FOLLOWUP_EVERY_H, AUDIT_RADIUS_DEFAULT_M, CATEGORY_LABELS,
    CATEGORY_MATERIAL, DUPLICATE_RADIUS_M, SLA_AT_RISK_FRACTION,
)
from app.models import AgentRun, AgentStep, Crew, HazardCluster, ServiceRequest, SlaPolicy, Ward
from app.models.enums import Role

OPEN = ("SUBMITTED", "ASSIGNED", "IN_PROGRESS", "ON_HOLD", "REOPENED")
SR_RE = re.compile(r"SR-\d{4}-\d{6}", re.I)

# ----------------------------------------------------------------------------- documents for retrieval
DOCS = [
    ("Citizen Charter: timelines", "Timelines are counted from the time the grievance is registered. They pause only for "
     "reasons outside the Corporation's control: waiting for another agency, weather, or information from the citizen. "
     "Every pause is recorded on the grievance."),
    ("Citizen Charter: priorities", "P1 is the most urgent: danger to life or property (live wire, open manhole, child fell). "
     "P4 is the least urgent. The system only gives P1 when the report has emergency words; an officer can raise it."),
    ("Citizen Charter: your rights", "Every grievance gets a Grievance Number and an acknowledgement, a named responsible "
     "officer and an expected resolution date, honest updates including the reason for any delay, before and after "
     "photographs when work is completed, and the right to reopen the grievance if the problem is not fixed."),
    ("FAQ: registration", "Citizens do not need to register or log in. A grievance can be lodged anonymously and tracked "
     "with the Grievance Number and the tracking code or mobile number."),
    ("FAQ: duplicates", "Similar reports at the same place are linked into one grievance (within "
     f"{min(DUPLICATE_RADIUS_M.values())}-{max(DUPLICATE_RADIUS_M.values())} m depending on the type). Every reporter "
     "still receives every update."),
    ("FAQ: other agencies", "Electricity feeders belong to BESCOM and water mains to BWSSB. The Corporation refers the "
     f"grievance to them and follows up every {AGENCY_FOLLOWUP_EVERY_H} hours; after {AGENCY_ESCALATE_AFTER_FOLLOWUPS} "
     "unanswered follow-ups it escalates to the Zonal Officer."),
    ("FAQ: reopening", "When asked to confirm the resolution, the citizen can choose Reopen and give the reason. A second "
     "reopen escalates the grievance to the next level."),
    ("FAQ: SMS", "Every update is sent by SMS in English or Kannada to the mobile number given."),
    ("Service rule: escalation", f"When {int(SLA_AT_RISK_FRACTION * 100)}% of the time is used the case is marked at "
     "risk and the Follow-up agent looks for the cause. When the deadline passes the case escalates level by level "
     "(L1 ward officer to L4 Commissioner); escalation never resets the clock."),
    ("Service rule: completion photos", "A crew must upload an after-photo. It must be taken after the job was assigned "
     f"and close to the site (50 m for potholes and streetlights, {AUDIT_RADIUS_DEFAULT_M} m otherwise), and must not "
     "be a reused photo. The Evidence Auditor sends work back on hard evidence; the Control Room gives final approval."),
    ("Service rule: vehicle feed", "Connected two-wheelers report road jolts. Only places hit by 3 or more different "
     "vehicles with good confidence become complaints; speed breakers and rail crossings are filtered out. Near an "
     "existing complaint the vehicle data is added as corroboration instead."),
    ("Service rule: heavy rain", "15 or more flood, drain or tree reports in one area within an hour (or a weather alert "
     "and 6 or more) opens an incident. The Control Room publishes the public advisory."),
]


def _n(x: int, one: str) -> str:
    return f"{x} {one if x == 1 else one + 's'}"


def _words(s: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", s.lower()) if len(w) > 2}


@tool("search_policies", "Search the Citizen Charter, FAQs and service rules (also the SLA timeline table). "
      "Returns the best matching passages with their source.", {"properties": props(query="string"), "required": ["query"]})
def search_policies(ctx, query: str):
    docs = list(DOCS)
    for p in ctx.db.scalars(select(SlaPolicy)):
        label = CATEGORY_LABELS.get(p.category, (p.category,))[0]
        docs.append((f"SLA timeline: {label} {p.priority}",
                     f"{label} ({p.category.lower().replace('_', ' ')}) at priority {p.priority}: resolve within "
                     f"{p.resolution_hours:g} hours ({p.resolution_hours / 24:g} days); citizen confirms within "
                     f"{p.verification_hours:g} hours."))
    q = _words(query)
    scored = sorted(((len(q & _words(t + " " + b)) + 2 * len(q & _words(t)), t, b) for t, b in docs), reverse=True)
    return [{"source": t, "text": b} for s, t, b in scored[:3] if s > 0] or [{"source": None, "text": "nothing relevant found"}]


# ----------------------------------------------------------------------------- live-data tools
def _sla(sr):
    from app.modules.sla.service import compute

    return compute(sr)


@tool("ward_summary", "Per ward: open cases, at risk, breached, escalated, new and resolved in the last N days, "
      "average days to resolve. Use for 'which ward is worst/best'.", {"properties": props(days=("integer", "window, default 7"))})
def ward_summary(ctx, days: int = 7):
    since = now() - timedelta(days=days)
    names = dict(ctx.db.execute(select(Ward.id, Ward.name)).all())
    agg: dict = defaultdict(lambda: Counter())
    durations: dict = defaultdict(list)
    for sr in ctx.db.scalars(select(ServiceRequest).where(ServiceRequest.ward_id.is_not(None))):
        a = agg[sr.ward_id]
        if sr.status in OPEN:
            a["open"] += 1
            st = _sla(sr).state
            a["at_risk"] += st == "AT_RISK"
            a["breached"] += st == "BREACHED"
            a["escalated"] += sr.escalation_level > 0
        if sr.created_at >= since:
            a["new"] += 1
        if sr.resolved_at and sr.resolved_at >= since:
            a["resolved"] += 1
            durations[sr.ward_id].append((sr.resolved_at - sr.created_at).total_seconds() / 86400)
    rows = [{"ward_id": w, "ward": names.get(w, w), **{k: a[k] for k in ("open", "at_risk", "breached", "escalated", "new", "resolved")},
             "avg_days_to_resolve": round(sum(durations[w]) / len(durations[w]), 1) if durations[w] else None}
            for w, a in agg.items()]
    return {"window_days": days, "wards": sorted(rows, key=lambda r: (-(r["breached"] * 2 + r["at_risk"]), r["ward_id"]))}


@tool("list_cases", "Open grievances matching filters (all optional), most urgent first.",
      {"properties": props(ward_id="string", category=("string", "e.g. POTHOLE, STREETLIGHT, GARBAGE"),
                           sla_state=("string", "ON_TRACK | AT_RISK | BREACHED | PAUSED"),
                           source=("string", "CITIZEN_WEB | VEHICLE_FEED"), limit="integer")})
def list_cases(ctx, ward_id: str | None = None, category: str | None = None, sla_state: str | None = None,
               source: str | None = None, limit: int = 8):
    q = select(ServiceRequest).where(ServiceRequest.status.in_(OPEN))
    if ward_id:
        q = q.where(ServiceRequest.ward_id == ward_id.upper())
    if category:
        q = q.where(ServiceRequest.category == category.upper())
    if source:
        q = q.where(ServiceRequest.source == source.upper())
    out = []
    for sr in ctx.db.scalars(q.order_by(ServiceRequest.priority, ServiceRequest.created_at)):
        v = _sla(sr)
        if sla_state and v.state != sla_state.upper():
            continue
        out.append({"sr_id": sr.id, "category": sr.category, "ward_id": sr.ward_id, "priority": sr.priority,
                    "status": sr.status, "sla": v.label, "sla_state": v.state, "source": sr.source,
                    "escalation_level": sr.escalation_level})
    return {"total": len(out), "cases": out[: max(1, min(limit, 15))]}


@tool("vehicle_findings", "What the connected-vehicle feed found: complaints it created on its own, citizen complaints "
      "it confirmed, failed repairs it flagged, weak spots waiting for review.", {"properties": {}})
def vehicle_findings(ctx):
    c = Counter(ctx.db.scalars(select(HazardCluster.status)))
    created = list(ctx.db.scalars(select(ServiceRequest).where(ServiceRequest.source == "VEHICLE_FEED")))
    return {"complaints_created_by_vehicles": len(created), "citizen_complaints_confirmed": c["CORROBORATED"],
            "failed_repairs_flagged": c["REPAIR_FAILURE"], "waiting_officer_review": c["REVIEW"],
            "filtered_out": c["FILTERED"],
            "vehicle_complaints_no_citizen_reported": sum(1 for s in created if s.reporter_count <= 1),
            "examples": [s.id for s in created[:5]]}


@tool("crew_overview", "Every field crew: open jobs vs capacity, overloaded or not, audit flag.",
      {"properties": props(ward_id="string")})
def crew_overview(ctx, ward_id: str | None = None):
    from app.agents.followup import crew_load

    q = select(Crew)
    if ward_id:
        q = q.where(Crew.ward_id == ward_id.upper())
    rows = []
    for cr in ctx.db.scalars(q.order_by(Crew.id)):
        n = crew_load(ctx.db, cr.id)
        rows.append({"crew_id": cr.id, "ward_id": cr.ward_id, "open_jobs": n, "capacity": cr.capacity,
                     "overloaded": n > cr.capacity, "audit_priority": cr.audit_priority})
    return {"crews": sorted(rows, key=lambda r: -r["open_jobs"] / max(r["capacity"], 1))}


# ----------------------------------------------------------------------------- agent
class AskAnswer(BaseModel):
    answer: str = Field(description="2-4 plain sentences answering the question, with the key numbers")
    points: list[str] = Field(default_factory=list, max_length=6, description="supporting facts, each from a tool result")
    cases: list[str] = Field(default_factory=list, max_length=8, description="grievance numbers the answer refers to")
    sources: list[str] = Field(default_factory=list, max_length=4, description="policy passages used, by source name")
    confidence: float = Field(ge=0, le=1)


CATEGORY_WORDS = {"pothole": "POTHOLE", "road": "POTHOLE", "streetlight": "STREETLIGHT", "light": "STREETLIGHT",
                  "garbage": "GARBAGE", "waste": "GARBAGE", "water": "WATER_LEAK", "leak": "WATER_LEAK",
                  "drain": "DRAIN_BLOCKED", "flood": "WATERLOGGING", "manhole": "OPEN_MANHOLE", "tree": "TREE_FALL"}


class AskAgent(Agent):
    name = "ask"
    label = "Ask CivicFlow"
    subject_type = "QUERY"
    tools = ["ward_summary", "list_cases", "vehicle_findings", "crew_overview", "search_policies", "get_case_timeline",
             "get_crew_load", "check_material_stock", "get_referral_status", "get_sla_policy"]
    max_steps = 6
    timeout_s = 40.0
    system_prompt = """You are Ask CivicFlow, the analyst the Commissioner and ward officers talk to.
Answer the question using the tools: live case data (ward_summary, list_cases, get_case_timeline, crew_overview,
vehicle_findings, ...) and search_policies for rules, timelines and citizen rights (quote the source name).
- Every number and grievance number in your answer must come from a tool result.
- For "why is a case late", look at the case timeline, the crew load and the material stock, then name the cause.
- If the data does not answer the question, say what is missing. Keep it short and plain."""

    def build_input(self, db, payload: dict):
        q = (payload.get("question") or "").strip()[:400]
        if not q:
            return None
        m = SR_RE.search(q)
        return {"question": q, "asked_by": payload.get("asked_by") or "Staff",
                "subject_id": m.group(0).upper() if m else None, "today": now().strftime("%d %b %Y")}

    def render_input(self, inp: dict) -> str:
        return f"Question from {inp['asked_by']} ({inp['today']}): {inp['question']}"

    def decision(self, out: AskAnswer) -> str:
        return out.answer.split(". ")[0][:160]

    def rationale(self, out: AskAnswer) -> str:
        return "\n".join(f"- {p}" for p in out.points)

    # ------------------------------------------------------------------ rule-based version
    def fallback(self, ctx: ToolContext, inp: dict) -> AskAnswer:
        q = inp["question"].lower()
        call = lambda name, args=None: ctx.call(name, args or {}, by="rules")  # noqa: E731
        cat = next((v for k, v in CATEGORY_WORDS.items() if k in q), None)
        ward = re.search(r"\bw\s?(\d{1,2})\b", q)
        ward_id = f"W{ward.group(1)}" if ward else None
        if inp.get("subject_id"):
            return self._why_case(call, inp["subject_id"])
        if re.search(r"charter|policy|rule|right|how long|deadline|timeline|reopen|bescom|bwssb|refer|sms|photo|escalat", q) \
                and not re.search(r"which|how many|worst|best", q):
            hits = call("search_policies", {"query": inp["question"]})
            top = [h for h in hits if h.get("source")]
            if top:
                return AskAnswer(answer=top[0]["text"], points=[h["text"] for h in top[1:]], sources=[h["source"] for h in top],
                                 confidence=0.7)
        if re.search(r"vehicle|sensor|detect|jolt|no citizen|nobody reported", q):
            v = call("vehicle_findings")
            return AskAnswer(
                answer=(f"The vehicle feed found {_n(v['complaints_created_by_vehicles'], 'problem')} on its own and filed "
                        f"{'it' if v['complaints_created_by_vehicles'] == 1 else 'them'} as complaints; "
                        f"{v['vehicle_complaints_no_citizen_reported']} of these no citizen has reported. It also confirmed "
                        f"{_n(v['citizen_complaints_confirmed'], 'citizen complaint')} and flagged "
                        f"{_n(v['failed_repairs_flagged'], 'failed repair')}."),
                points=[f"{v['waiting_officer_review']} weak spots are waiting for an officer to review",
                        f"{v['filtered_out']} spots were filtered out (speed breakers, single vehicles)"],
                cases=v["examples"], confidence=0.85)
        if re.search(r"crew|team|overload|workload|capacity", q):
            c = call("crew_overview", {"ward_id": ward_id} if ward_id else {})["crews"]
            over = [x for x in c if x["overloaded"]]
            top = c[0] if c else None
            return AskAnswer(
                answer=(f"{len(over)} of {len(c)} crews {'is' if len(over) == 1 else 'are'} overloaded" + (f"; the busiest is {top['crew_id']} with "
                        f"{top['open_jobs']} open jobs for {top['capacity']} slots." if top else ".")),
                points=[f"{x['crew_id']} ({x['ward_id']}): {x['open_jobs']}/{x['capacity']} jobs" for x in c[:5]]
                + [f"{x['crew_id']} is under quality review" for x in c if x["audit_priority"] == "HIGH"][:2],
                confidence=0.85)
        if re.search(r"breach|overdue|late|delay|at risk|escalat", q) or cat:
            state = "AT_RISK" if "risk" in q else ("BREACHED" if re.search(r"breach|overdue|late", q) else None)
            r = call("list_cases", {k: v for k, v in {"sla_state": state, "category": cat, "ward_id": ward_id}.items() if v})
            what = " ".join(x for x in [(state or "open").replace("_", " ").lower(),
                                        cat.replace("_", " ").lower() if cat else "", "grievances",
                                        f"in {ward_id}" if ward_id else ""] if x)
            return AskAnswer(answer=f"There are {r['total']} {what}.",
                             points=[f"{c['sr_id']}: {c['category'].replace('_', ' ').lower()}, {c['ward_id']}, {c['priority']}, {c['sla']}"
                                     for c in r["cases"][:6]],
                             cases=[c["sr_id"] for c in r["cases"][:8]], confidence=0.85)
        # default: how are the wards doing
        days = 30 if "month" in q else 7
        w = call("ward_summary", {"days": days})["wards"]
        if not w:
            return AskAnswer(answer="There is no case data yet.", confidence=0.5)
        worst, best = w[0], w[-1]
        return AskAnswer(
            answer=(f"{worst['ward_id']} {worst['ward']} needs the most attention: {worst['breached']} breached and "
                    f"{worst['at_risk']} at-risk cases out of {worst['open']} open. {best['ward_id']} {best['ward']} is "
                    f"doing best with {best['breached']} breached."),
            points=[f"{x['ward_id']} {x['ward']}: {x['open']} open, {x['at_risk']} at risk, {x['breached']} breached, "
                    f"{x['resolved']} resolved in {days} days" + (f" (avg {x['avg_days_to_resolve']} days)" if x["avg_days_to_resolve"] else "")
                    for x in w],
            confidence=0.8)

    def _why_case(self, call, sr_id: str) -> AskAnswer:
        t = call("get_case_timeline", {"sr_id": sr_id})
        if "error" in t:
            return AskAnswer(answer=f"I could not find {sr_id}.", confidence=0.9)
        causes, points = [], [f"Status {t['status'].replace('_', ' ').lower()}, priority {t['priority']}, SLA {t['sla']['label']}"]
        wos = [w for w in t["work_orders"] if w["status"] not in ("VERIFIED", "CANCELLED")]
        if t["status"] == "SUBMITTED":
            causes.append("it has not been accepted by the ward officer yet, so no crew is assigned")
        for w in wos:
            load = call("get_crew_load", {"crew_id": w["crew_id"]})
            points.append(f"{w['wo_id']} with crew {w['crew_id']}: {w['status'].replace('_', ' ').lower()}, "
                          f"crew has {load.get('open_jobs')}/{load.get('capacity')} jobs")
            if load.get("overloaded"):
                causes.append(f"crew {w['crew_id']} is overloaded ({load['open_jobs']} jobs for {load['capacity']} slots)")
            if not w["started"]:
                causes.append("the work has not started")
        mat = CATEGORY_MATERIAL.get(t["category"])
        if mat and t["status"] in OPEN:
            stock = call("check_material_stock", {"item": mat[0]})
            if stock.get("in_stock") is False:
                causes.append(f"{stock.get('name', mat[0])} is out of stock")
        for r in t["referrals"]:
            ref = call("get_referral_status", {"referral_id": r["referral_id"]})
            if ref.get("agency_status") not in ("RESOLVED", "CLOSED"):
                causes.append(f"it is waiting on {r['agency']} ({ref.get('followups_sent', 0)} follow-ups sent)")
        sla = t["sla"]["state"]
        head = f"{sr_id} is {sla.replace('_', ' ').lower()} ({t['sla']['label']})."
        answer = head + (" Main reason: " + "; ".join(dict.fromkeys(causes)) + "." if causes else " Nothing is blocking it right now.")
        return AskAnswer(answer=answer, points=points, cases=[sr_id], confidence=0.85 if causes else 0.7)


ask_agent = AskAgent()

# ----------------------------------------------------------------------------- API
router = APIRouter(tags=["agents"])


class AskIn(BaseModel):
    question: str = Field(min_length=3, max_length=400)


def _answer(db: Session, run: AgentRun) -> dict:
    from app.agents.flow import _how, _plain_step

    steps = db.scalars(select(AgentStep).where(AgentStep.run_id == run.id).order_by(AgentStep.idx)).all()
    out = run.output or {}
    return {"run_id": run.id, "question": (run.input_summary or {}).get("question"), "at": run.started_at,
            "answer": out.get("answer") or "Sorry, I could not answer that.", "points": out.get("points", []),
            "cases": out.get("cases", []), "sources": out.get("sources", []), "confidence": run.confidence,
            "how": _how(run.model), "latency_ms": run.latency_ms,
            "steps": [{"n": i + 1, **_plain_step(s)} for i, s in enumerate(steps)]}


@router.post("/ask")
def ask(body: AskIn, db: Session = Depends(get_db),
        actor=Depends(require_roles(Role.CONTROL_ROOM, Role.WARD_OFFICER))):
    from app.agents.runtime.loop import run_agent
    from app.models import User

    user = db.get(User, actor.user_id) if actor.user_id else None
    run_id = run_agent(ask_agent, "staff.question", {"question": body.question, "asked_by": user.name if user else "Staff"})
    db.expire_all()
    run = db.get(AgentRun, run_id) if run_id else None
    if run is None:
        return {"run_id": None, "question": body.question, "answer": "Sorry, I could not answer that right now.",
                "points": [], "cases": [], "sources": [], "steps": [], "how": None, "confidence": None}
    return _answer(db, run)


@router.get("/ask/history")
def history(db: Session = Depends(get_db), actor=Depends(require_roles(Role.CONTROL_ROOM, Role.WARD_OFFICER))):
    runs = db.scalars(select(AgentRun).where(AgentRun.agent == "ask").order_by(AgentRun.id.desc()).limit(5))
    return [_answer(db, r) for r in runs]
