"""Agent 2: Follow-up & Escalation.

Triggers (all produced by deterministic code, so the agent runs on state CHANGES, not every tick):
  sla.at_risk        -> diagnose why a case is late and propose a fix before the deadline
  sla.breached       -> write the honest reason onto the escalation the rule engine just raised
  agency.followup_due-> chase BESCOM/BWSSB; after 2 unanswered follow-ups escalate to the Zonal Officer
Acts alone: agency follow-ups, notifications, material requests, the escalation write-up.
Needs a human: crew reassignment (officer Approve), SLA pause/waiver.
"""
from __future__ import annotations

import math
from datetime import timedelta
from typing import Literal

from pydantic import BaseModel, Field
from sqlalchemy import func, select

from app.agents.runtime.base import Agent
from app.agents.runtime.tools import ToolContext, note, props, tool
from app.core.clock import IST, now
from app.domain_config import (
    AGENCY_ESCALATE_AFTER_FOLLOWUPS, AGENCY_FOLLOWUP_EVERY_H, CATEGORY_MATERIAL, CATEGORY_SKILL,
)
from app.models import (
    AgencyMessage, Crew, Escalation, Inventory, MaterialRequest, ReassignmentProposal, Referral, ServiceRequest,
    StatusEvent, Timeline, User, WorkOrder,
)
from app.modules import geo
from app.modules.notifications.service import notify_citizen, notify_staff

OPEN_WO = ("ASSIGNED", "IN_PROGRESS", "REWORK", "ON_HOLD")
AGENCY_NAMES = {"BESCOM": "BESCOM", "BWSSB": "BWSSB", "BMRCL": "BMRCL"}


# ----------------------------------------------------------------------------- read tools
@tool("get_case_timeline", "Status history, escalations, referrals and work orders of a grievance.",
      {"properties": props(sr_id="string"), "required": ["sr_id"]})
def get_case_timeline(ctx, sr_id: str):
    from app.modules.sla.service import compute

    sr = ctx.db.get(ServiceRequest, sr_id)
    if sr is None:
        return {"error": f"no grievance {sr_id}"}
    v = compute(sr)
    evs = ctx.db.scalars(select(StatusEvent).where(StatusEvent.object_id == sr.id).order_by(StatusEvent.at)).all()
    wos = ctx.db.scalars(select(WorkOrder).where(WorkOrder.sr_id == sr.id)).all()
    refs = ctx.db.scalars(select(Referral).where(Referral.sr_id == sr.id)).all()
    return {"sr_id": sr.id, "category": sr.category, "priority": sr.priority, "status": sr.status,
            "ward_id": sr.ward_id, "hold_reason": sr.hold_reason, "escalation_level": sr.escalation_level,
            "sla": {"state": v.state, "label": v.label, "elapsed_fraction": round(v.fraction or 0, 2)},
            "history": [{"at": e.at.astimezone(IST).strftime("%d %b %H:%M"), "to": e.to_state, "by": e.actor_type} for e in evs][-8:],
            "work_orders": [{"wo_id": w.id, "crew_id": w.crew_id, "status": w.status, "materials": w.materials,
                             "assigned_at": w.assigned_at.astimezone(IST).strftime("%d %b %H:%M"),
                             "started": w.started_at is not None} for w in wos],
            "referrals": [{"referral_id": r.id, "agency": r.agency, "status": r.status, "agency_status": r.agency_status,
                           "followups_sent": r.followups_sent} for r in refs]}


def crew_load(db, crew_id: str) -> int:
    return db.scalar(select(func.count()).select_from(WorkOrder).where(WorkOrder.crew_id == crew_id,
                                                                     WorkOrder.status.in_(OPEN_WO))) or 0


@tool("get_crew_load", "Open jobs vs capacity for a crew.", {"properties": props(crew_id="string"), "required": ["crew_id"]})
def get_crew_load(ctx, crew_id: str):
    c = ctx.db.get(Crew, crew_id)
    if c is None:
        return {"error": f"no crew {crew_id}"}
    load = crew_load(ctx.db, crew_id)
    return {"crew_id": c.id, "ward_id": c.ward_id, "skills": c.skills, "open_jobs": load, "capacity": c.capacity,
            "overloaded": load > c.capacity}


@tool("find_available_crews", "Crews with spare capacity and the needed skill near a site (own ward and neighbouring wards).",
      {"properties": props(sr_id="string", skill="string", radius_km=("number", "default 3")), "required": ["sr_id"]})
def find_available_crews(ctx, sr_id: str, skill: str | None = None, radius_km: float = 3):
    sr = ctx.db.get(ServiceRequest, sr_id)
    lat, lon = geo.latlon(sr.location)
    skill = skill or CATEGORY_SKILL.get(sr.category, "ROADS")
    out = []
    for c in ctx.db.scalars(select(Crew)):
        if skill not in (c.skills or []):
            continue
        d = geo.distance_m((lat, lon), geo.latlon(c.base_location)) / 1000
        load = crew_load(ctx.db, c.id)
        if d <= radius_km and load < c.capacity:
            out.append({"crew_id": c.id, "ward_id": c.ward_id, "distance_km": round(d, 1), "open_jobs": load,
                        "capacity": c.capacity, "same_ward": c.ward_id == sr.ward_id})
    return sorted(out, key=lambda x: (x["open_jobs"] / max(x["capacity"], 1), x["distance_km"]))


@tool("check_material_stock", "Stock of a material item (e.g. cold_mix_bitumen, led_driver_40w).",
      {"properties": props(item="string"), "required": ["item"]})
def check_material_stock(ctx, item: str):
    inv = ctx.db.get(Inventory, item)
    if inv is None:
        return {"error": f"unknown item {item}"}
    return {"item": inv.item, "name": inv.name, "qty": inv.qty, "unit": inv.unit, "in_stock": inv.qty > 0,
            "out_since": inv.out_since.astimezone(IST).strftime("%d %b") if inv.out_since and inv.qty <= 0 else None}


@tool("get_referral_status", "Status of an inter-agency referral and the messages exchanged.",
      {"properties": props(referral_id="integer"), "required": ["referral_id"]})
def get_referral_status(ctx, referral_id: int):
    r = ctx.db.get(Referral, referral_id)
    if r is None:
        return {"error": f"no referral {referral_id}"}
    msgs = ctx.db.scalars(select(AgencyMessage).where(AgencyMessage.referral_id == r.id).order_by(AgencyMessage.id)).all()
    return {"referral_id": r.id, "sr_id": r.sr_id, "agency": r.agency, "status": r.status, "agency_status": r.agency_status,
            "sent": r.sent_at.astimezone(IST).strftime("%d %b %H:%M") if r.sent_at else None, "followups_sent": r.followups_sent,
            "last_followup": r.last_followup_at.astimezone(IST).strftime("%d %b %H:%M") if r.last_followup_at else None,
            "agency_reply": r.agency_reply, "messages": [{"dir": m.direction, "body": m.body[:160]} for m in msgs[-4:]]}


# ----------------------------------------------------------------------------- action tools (called from apply)
@tool("send_agency_followup", "Send a follow-up message to the agency for a referral (simulated agency inbox).",
      {"properties": props(referral_id="integer", message="string"), "required": ["referral_id", "message"]})
def send_agency_followup(ctx, referral_id: int, message: str):
    from app.adapters.agency import agency_adapter

    r = ctx.db.get(Referral, referral_id)
    r.followups_sent = (r.followups_sent or 0) + 1
    r.last_followup_at = now()
    agency_adapter.send(ctx.db, r, f"Follow-up #{r.followups_sent}: {message}")
    return {"referral_id": r.id, "followups_sent": r.followups_sent}


@tool("propose_reassignment", "Propose moving a work order to another crew (an officer must approve).",
      {"properties": props(wo_id="string", crew_id="string", reason="string"), "required": ["wo_id", "crew_id", "reason"]})
def propose_reassignment(ctx, wo_id: str, crew_id: str, reason: str):
    wo = ctx.db.get(WorkOrder, wo_id)
    existing = ctx.db.scalar(select(ReassignmentProposal).where(ReassignmentProposal.wo_id == wo_id,
                                                               ReassignmentProposal.status == "PENDING"))
    if existing:
        return {"proposal_id": existing.id, "note": "already pending"}
    sr = ctx.db.get(ServiceRequest, wo.sr_id)
    to = ctx.db.get(Crew, crew_id)
    dist = geo.distance_m(geo.latlon(sr.location), geo.latlon(to.base_location)) / 1000
    p = ReassignmentProposal(wo_id=wo_id, from_crew_id=wo.crew_id, to_crew_id=crew_id, reason=reason,
                             distance_km=round(dist, 1), status="PENDING", agent_run_id=ctx.run_id, created_at=now())
    ctx.db.add(p)
    ctx.db.flush()
    return {"proposal_id": p.id, "distance_km": p.distance_km}


@tool("raise_material_request", "Raise a material request to stores.",
      {"properties": props(item="string", qty="number", sr_id="string"), "required": ["item", "qty"]})
def raise_material_request(ctx, item: str, qty: float, sr_id: str | None = None):
    if ctx.db.scalar(select(MaterialRequest).where(MaterialRequest.item == item, MaterialRequest.sr_id == sr_id,
                                                   MaterialRequest.status == "RAISED")):
        return {"note": "already requested"}
    m = MaterialRequest(item=item, qty=qty, sr_id=sr_id, status="RAISED", agent_run_id=ctx.run_id, created_at=now())
    ctx.db.add(m)
    ctx.db.flush()
    return {"material_request_id": m.id}


@tool("escalate", "Escalate a grievance one level with a written reason (never resets the SLA clock).",
      {"properties": props(sr_id="string", level="integer", reason_summary="string", trigger="string"),
       "required": ["sr_id", "level", "reason_summary"]})
def escalate_tool(ctx, sr_id: str, level: int, reason_summary: str, trigger: str = "AGENCY_NO_RESPONSE"):
    from app.modules.sla.engine import escalate

    e = escalate(ctx.db, ctx.db.get(ServiceRequest, sr_id), level, trigger, reason_summary, ctx.run_id)
    return {"escalated": e is not None, "level": e.level if e else None}


@tool("notify_officer", "Send an internal message to an officer.",
      {"properties": props(officer_id="integer", message="string", sr_id="string"), "required": ["officer_id", "message"]})
def notify_officer(ctx, officer_id: int, message: str, sr_id: str | None = None):
    nid = notify_staff(ctx.db, officer_id, "AGENT_NOTE", message, sr_id, dedupe=f"{ctx.run_id}")
    return {"sent": nid is not None}


# ----------------------------------------------------------------------------- agent
class FollowupDecision(BaseModel):
    sr_id: str
    situation: Literal["AT_RISK", "BREACHED", "AGENCY_FOLLOWUP"]
    diagnosis: list[Literal["CREW_OVERLOAD", "MATERIAL_OUT", "AGENCY_PENDING", "NOT_STARTED", "UNASSIGNED", "OTHER"]]
    explanation: str = Field(description="One or two plain sentences: WHY the case is late (facts, dates). Used as the escalation reason.")
    citizen_message: str = Field(description="Polite, honest, plain-language update for the citizen (no internal IDs except the grievance no.)")
    officer_message: str | None = None
    reassign_wo_id: str | None = None
    reassign_to_crew: str | None = None
    material_item: str | None = None
    material_qty: float | None = None
    agency_followup_message: str | None = None
    rationale: list[str] = Field(min_length=1, max_length=6)
    confidence: float = Field(ge=0, le=1)


SYSTEM = """You are the Follow-up & Escalation officer for CivicFlow Municipal Corporation. No case may sit idle.
You are called when (a) a case reaches 75% of its SLA (AT_RISK), (b) it has breached its SLA (BREACHED; the rule engine
has already escalated it and you write the reason), or (c) an inter-agency referral is due for follow-up (AGENCY_FOLLOWUP).
Find out WHY it is late using the tools: is the crew overloaded (get_crew_load)? is material out of stock
(check_material_stock: the work order's materials)? is it waiting on BESCOM/BWSSB (get_referral_status)? has no one started?
Then propose the fix:
- crew overloaded -> find_available_crews (other wards allowed) and set reassign_wo_id + reassign_to_crew (an officer approves)
- material out -> set material_item + material_qty
- agency pending -> agency_followup_message (short, firm, polite)
explanation: the honest reason in one or two sentences with dates, e.g. "Delayed because LED drivers have been out of stock
since 3 Nov and crew W12-B has 6 jobs for 4 slots; not inaction."
citizen_message: tell the citizen the honest reason and what is being done, in plain words."""


class FollowupAgent(Agent):
    name = "followup"
    label = "Follow-up & Escalation"
    system_prompt = SYSTEM
    triggers = ["sla.at_risk", "sla.breached", "agency.followup_due"]
    output_model = FollowupDecision
    max_steps = 8
    timeout_s = 60.0
    tools = ["get_case_timeline", "get_crew_load", "find_available_crews", "check_material_stock", "get_referral_status",
             "get_sensitive_places_nearby"]

    def build_input(self, db, payload):
        situation = {"sla.at_risk": "AT_RISK", "sla.breached": "BREACHED"}.get(payload.get("_event"), "AGENCY_FOLLOWUP")
        sr = db.get(ServiceRequest, payload.get("id") or payload.get("sr_id"))
        if sr is None or sr.status in ("CLOSED", "REJECTED", "MERGED", "RESOLVED"):
            return None
        inp = {"subject_id": sr.id, "sr_id": sr.id, "situation": situation, "category": sr.category,
               "priority": sr.priority, "status": sr.status, "ward_id": sr.ward_id}
        if situation == "AGENCY_FOLLOWUP":
            inp["referral_id"] = payload["referral_id"]
        return inp

    def decision(self, out: FollowupDecision) -> str:
        acts = []
        if out.reassign_to_crew:
            acts.append(f"propose {out.reassign_to_crew}")
        if out.material_item:
            acts.append(f"request {out.material_item}")
        if out.agency_followup_message:
            acts.append("agency follow-up")
        return f"{out.situation}: {'+'.join(out.diagnosis) or 'checked'}" + (f" -> {', '.join(acts)}" if acts else "")

    # ---------------------------------------------------------------- rule-based diagnosis
    def facts(self, ctx: ToolContext, inp: dict, by: str) -> dict:
        tl = ctx.call("get_case_timeline", {"sr_id": inp["sr_id"]}, by=by)
        f = {"diagnosis": [], "reasons": [], "overloaded_wo": None, "material": None, "referral": None, "crew_alt": None}
        open_wos = [w for w in tl["work_orders"] if w["status"] in OPEN_WO]
        if not tl["work_orders"]:
            f["diagnosis"].append("UNASSIGNED")
            f["reasons"].append("no work order has been created yet")
        for w in open_wos:
            load = ctx.call("get_crew_load", {"crew_id": w["crew_id"]}, by=by)
            if load.get("overloaded"):
                f["diagnosis"].append("CREW_OVERLOAD")
                f["overloaded_wo"] = w["wo_id"]
                f["reasons"].append(f"crew {w['crew_id']} has {load['open_jobs']} open jobs for {load['capacity']} slots")
            for item, qty in (w.get("materials") or {}).items():
                st = ctx.call("check_material_stock", {"item": item}, by=by)
                if not st.get("in_stock", True):
                    f["diagnosis"].append("MATERIAL_OUT")
                    f["material"] = (item, qty)
                    since = f" since {st['out_since']}" if st.get("out_since") else ""
                    f["reasons"].append(f"{st['name'].lower()} is out of stock{since}")
            if not w["started"] and "CREW_OVERLOAD" not in f["diagnosis"]:
                f["diagnosis"].append("NOT_STARTED")
                f["reasons"].append(f"crew {w['crew_id']} has not started the work yet")
        for r in tl["referrals"]:
            if r["status"] == "SENT" and r["agency_status"] in ("NO_RESPONSE", "ACKNOWLEDGED", "IN_PROGRESS"):
                st = ctx.call("get_referral_status", {"referral_id": r["referral_id"]}, by=by)
                f["diagnosis"].append("AGENCY_PENDING")
                f["referral"] = st
                fu = f"; we have followed up {st['followups_sent']} time{'s' if st['followups_sent'] != 1 else ''}" if st["followups_sent"] else ""
                f["reasons"].append(f"waiting for {r['agency']} to act (referred {st['sent']}{fu})")
        if f["overloaded_wo"]:
            alts = ctx.call("find_available_crews", {"sr_id": inp["sr_id"], "radius_km": 3}, by=by)
            if alts:
                f["crew_alt"] = alts[0]
        if not f["diagnosis"]:
            f["diagnosis"].append("OTHER")
        f["tl"] = tl
        return f

    def fallback(self, ctx, inp):
        f = self.facts(ctx, inp, "rules")
        sit = inp["situation"]
        reasons = f["reasons"] or ["no blocking cause found in the records"]
        explanation = "Delayed because " + "; ".join(reasons) + "." + ("" if "OTHER" in f["diagnosis"] else " Not inaction.")
        alt = f["crew_alt"]
        why = [r[0].upper() + r[1:] + "." for r in reasons]
        if alt:
            why.append(f"Crew {alt['crew_id']} ({alt['ward_id']}) has {alt['open_jobs']}/{alt['capacity']} jobs and is "
                       f"{alt['distance_km']} km away: reassignment proposed.")
        if f["material"]:
            why.append(f"Material request raised for {f['material'][1]:g} of {f['material'][0]}.")
        citizen = {
            "AT_RISK": "Your grievance {sr} may be delayed: {why}. We are {fix}.",
            "BREACHED": "Your grievance {sr} is overdue: {why}. It has been escalated to a senior officer, and we are {fix}.",
            "AGENCY_FOLLOWUP": "Update on {sr}: {why}. We are following up with them and will keep you informed.",
        }[sit]
        fixes = []
        if alt:
            fixes.append("moving it to a free crew nearby")
        if f["material"]:
            fixes.append("arranging the material")
        if f["referral"]:
            fixes.append(f"following up with {f['referral']['agency']}")
        fix = " and ".join(fixes) or "monitoring it closely"
        msg = citizen.format(sr=inp["sr_id"], why="; ".join(reasons), fix=fix)
        agency_msg = None
        if f["referral"]:
            r = f["referral"]
            agency_msg = (f"Grievance {inp['sr_id']} referred to {r['agency']} on {r['sent']} is still pending. "
                          f"Citizens are affected; please confirm the repair date.")
        return FollowupDecision(
            sr_id=inp["sr_id"], situation=sit, diagnosis=sorted(set(f["diagnosis"])), explanation=explanation,
            citizen_message=msg, officer_message=None, reassign_wo_id=f["overloaded_wo"] if alt else None,
            reassign_to_crew=alt["crew_id"] if alt else None,
            material_item=f["material"][0] if f["material"] else None,
            material_qty=f["material"][1] if f["material"] else None,
            agency_followup_message=agency_msg, rationale=why[:6], confidence=0.8)

    # ---------------------------------------------------------------- deterministic side effects
    def apply(self, ctx, inp, out: FollowupDecision):
        db = ctx.db
        sr = db.get(ServiceRequest, inp["sr_id"])
        sit = inp["situation"]
        owner = db.get(User, sr.owner_id) if sr.owner_id else None
        # reassignment: only to a real crew with the skill and spare capacity; an officer approves
        if out.reassign_to_crew and out.reassign_wo_id:
            wo, crew = db.get(WorkOrder, out.reassign_wo_id), db.get(Crew, out.reassign_to_crew)
            ok = (wo is not None and wo.sr_id == sr.id and wo.status in OPEN_WO and crew is not None
                  and CATEGORY_SKILL.get(sr.category, "ROADS") in (crew.skills or [])
                  and crew_load(db, crew.id) < crew.capacity and crew.id != wo.crew_id)
            if ok:
                ctx.call("propose_reassignment", {"wo_id": wo.id, "crew_id": crew.id, "reason": out.explanation}, by="apply")
            else:
                note(ctx, "reassignment_rejected", {"crew": out.reassign_to_crew, "reason": "crew unsuitable or busy"})
        if out.material_item and db.get(Inventory, out.material_item):
            ctx.call("raise_material_request", {"item": out.material_item, "qty": out.material_qty or 1, "sr_id": sr.id}, by="apply")
        if sit == "BREACHED":
            e = db.scalar(select(Escalation).where(Escalation.sr_id == sr.id).order_by(Escalation.id.desc()).limit(1))
            if e is not None:
                e.reason_summary, e.agent_run_id = out.explanation, ctx.run_id
        if sit == "AGENCY_FOLLOWUP":
            r = db.get(Referral, inp["referral_id"])
            if r and r.status == "SENT" and r.agency_status == "NO_RESPONSE":
                msg = out.agency_followup_message or f"Grievance {sr.id} is still pending; please confirm action."
                ctx.call("send_agency_followup", {"referral_id": r.id, "message": msg}, by="apply")
                if r.followups_sent >= AGENCY_ESCALATE_AFTER_FOLLOWUPS:
                    sent = r.sent_at.astimezone(IST).strftime("%d %b") if r.sent_at else "earlier"
                    reason = (f"Awaiting {r.agency} ({r.reason.split(';')[0].strip()}); referred {sent} and followed up "
                              f"{r.followups_sent} times with no response. Not municipal inaction.")
                    ctx.call("escalate", {"sr_id": sr.id, "level": max(2, sr.escalation_level + 1),
                                          "reason_summary": reason, "trigger": "AGENCY_NO_RESPONSE"}, by="apply")
                    out.explanation = reason
        if owner and sit != "AGENCY_FOLLOWUP":
            ctx.call("notify_officer", {"officer_id": owner.id, "sr_id": sr.id,
                                        "message": f"{sr.id} {sit.replace('_', ' ').lower()}: {out.explanation}"
                                                   + (f" Proposed: reassign to {out.reassign_to_crew}." if out.reassign_to_crew else "")}, by="apply")
        notify_citizen(db, sr, "DELAY", body_en=f"CivicFlow: {out.citizen_message}", dedupe=f"{sit}-{ctx.run_id}",
                       extra={"reason": out.citizen_message})
        note(ctx, "citizen_notified", {"event": "DELAY", "message": out.citizen_message})
        db.add(Timeline(sr_id=sr.id, stage="Delay Update", remarks=out.citizen_message, actor_type="AGENT", at=now()))


followup = FollowupAgent()


# ----------------------------------------------------------------------------- referral follow-up timer
def due_referrals(db) -> list[Referral]:
    every = timedelta(hours=AGENCY_FOLLOWUP_EVERY_H)
    out = []
    for r in db.scalars(select(Referral).where(Referral.status == "SENT", Referral.agency_status == "NO_RESPONSE")):
        last = r.last_followup_at or r.sent_at
        if last and now() - last >= every:
            out.append(r)
    return out


def run_followup_timer() -> None:
    from app.agents.runtime.loop import run_agent
    from app.core.db import SessionLocal

    db = SessionLocal()
    try:
        due = [(r.id, r.sr_id) for r in due_referrals(db)]
    finally:
        db.close()
    for rid, sr_id in due:
        run_agent(followup, "agency.followup_due", {"_event": "agency.followup_due", "sr_id": sr_id, "referral_id": rid})


def ceil_div(a, b):
    return math.ceil(a / b)
