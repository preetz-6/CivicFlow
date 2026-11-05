"""Agent 1: Case Investigator. Trigger: complaint.submitted, complaint.reopened.

Investigates like a senior ward engineer and writes a TriageBrief. Acts on its own only for safe,
reversible steps (queue placement, >=0.9 duplicate merge, referral DRAFT, acknowledgement); the ward
officer Accepts or Overrides.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select

from app.agents import common_tools  # noqa: F401  (register tools)
from app.agents import vision  # noqa: F401
from app.agents.runtime import notify  # noqa: F401
from app.agents.runtime.base import Agent
from app.agents.runtime.tools import ToolContext, note
from app.core.clock import now
from app.domain_config import (
    CATEGORY_DEPARTMENT, CATEGORY_LABELS, DEFAULT_PRIORITY, DUPLICATE_RADIUS_M, DUPLICATE_WINDOW_HOURS,
)
from app.models import AuditLog, Department, ServiceRequest, Timeline, User
from app.models.enums import Category
from app.modules import geo
from app.modules.complaints.service import apply_sla, is_emergency
from app.modules.notifications.service import notify_citizen

PRIORITIES = ["P1", "P2", "P3", "P4"]
MERGE_THRESHOLD = 0.9
SENSITIVE_TYPES = {"SCHOOL", "HOSPITAL", "BUS_STAND", "MARKET", "METRO"}
ASSET_TYPE_FOR = {"STREETLIGHT": "STREETLIGHT", "DRAIN_BLOCKED": "DRAIN", "WATERLOGGING": "DRAIN",
                  "WATER_LEAK": "WATER_MAIN"}


class Referral(BaseModel):
    agency: Literal["BESCOM", "BWSSB", "BMRCL"]
    reason: str


class TriageBrief(BaseModel):
    category: str = Field(description="Category; may correct the citizen's choice")
    priority: Literal["P1", "P2", "P3", "P4"]
    department_id: str
    ward_id: str | None
    suggested_officer_id: int | None = None
    asset_id: str | None = None
    duplicate_of: str | None = None
    duplicate_confidence: float = Field(0.0, ge=0, le=1)
    repeat_failure: bool = False
    repeat_failure_note: str | None = None
    planned_work_conflict: str | None = None
    interagency_referral: Referral | None = None
    vehicle_corroboration: int = Field(0, description="distinct connected vehicles that detected this hazard")
    rationale: list[str] = Field(min_length=1, max_length=6, description="3-5 short bullets for the officer")
    citizen_summary: str | None = Field(None, description="One plain-language sentence for the citizen timeline")
    confidence: float = Field(ge=0, le=1)

    @field_validator("category")
    @classmethod
    def _cat(cls, v):
        if v not in Category.__members__:
            raise ValueError(f"category must be one of {list(Category.__members__)}")
        return v


SYSTEM = """You are the Case Investigator for CivicFlow Municipal Corporation (Kengeri / RR Nagar, Bengaluru).
A citizen (or a connected-vehicle data feed) has just filed a grievance. Investigate it the way a senior ward
engineer would and produce a triage brief for the ward officer.

Work through:
1. Ward and owning department (category -> department: POTHOLE/DAMAGED_ROAD->ROADS, STREETLIGHT->LIGHTING,
   GARBAGE->SWM, DRAIN_BLOCKED/WATERLOGGING/OPEN_MANHOLE->SWD, WATER_LEAK->WATER, TREE_FALL->PARKS).
2. If there is a photo, check that it matches the category; correct the category only if the photo clearly shows something else.
3. The nearest relevant asset and its history: 2+ repairs in 60 days is a REPEAT FAILURE; several open complaints
   on the same feeder/stretch suggests an upstream fault (e.g. a BESCOM feeder) rather than one bad fitting.
4. Who owns the asset. BESCOM (electricity) or BWSSB (water) ownership -> propose an inter-agency referral.
5. Duplicates: an open complaint of the same category within ~25-100 m filed in the last 72 h, with similar text,
   is likely the same issue. duplicate_confidence >= 0.9 means you are sure (it will be merged automatically).
6. Priority: P1 only for danger to life (live wire, open manhole, someone fell). Raise by one level (towards P2)
   near a school, hospital, bus stand, market or metro (within ~150 m), on an arterial road, when several citizens
   report it, or when connected vehicles confirm it. Otherwise use the category default (P3 for most).
7. Planned works nearby (metro, pipeline, cabling) that may have caused it or will conflict with repair.

Rationale: 3-5 bullets, each citing a fact you looked up (e.g. "Pole STREETLIGHT-W12-00871 repaired 48 and 19 days ago").
citizen_summary: one short plain sentence a citizen will see, no internal IDs other than the grievance number."""


class CaseInvestigator(Agent):
    name = "investigator"
    label = "Case Investigator"
    system_prompt = SYSTEM
    triggers = ["complaint.submitted", "complaint.reopened"]
    output_model = TriageBrief
    max_steps = 8
    timeout_s = 60.0
    tools = [
        "get_ward_for_location", "find_nearby_assets", "get_asset_history", "find_nearby_open_complaints",
        "get_planned_works", "get_asset_owner", "get_sensitive_places_nearby", "get_vehicle_detections_nearby",
        "get_sla_policy", "get_officer_workload", "analyze_photo", "get_road_class",
    ]

    # ------------------------------------------------------------------ input
    def build_input(self, db, payload: dict) -> dict | None:
        sr = db.get(ServiceRequest, payload["id"])
        if sr is None or sr.status not in ("SUBMITTED", "REOPENED"):
            return None
        lat, lon = geo.latlon(sr.location)
        return {
            "subject_id": sr.id, "grievance_no": sr.id, "category_chosen": sr.category,
            "description": sr.description, "lat": lat, "lon": lon, "landmark": sr.landmark,
            "address": sr.address, "source": sr.source, "status": sr.status, "reopen_count": sr.reopen_count,
            "filed_at": sr.created_at.isoformat(), "photo_attachment_ids": common_tools.photo_ids(db, sr.id),
            "emergency_keywords_found": is_emergency(sr.description),
        }

    @staticmethod
    def rule_duplicate(nearby_same: list[dict], inp: dict) -> tuple[str | None, float]:
        """Brief 5.2 duplicate rule: same category, within the category radius, within 72 h, similar text."""
        cat = inp["category_chosen"]
        dup, dup_conf = None, 0.0
        radius = DUPLICATE_RADIUS_M.get(cat, 50)
        for c in nearby_same:
            if c["category"] != cat or c["distance_m"] > radius or c["hours_ago"] > DUPLICATE_WINDOW_HOURS:
                continue
            if c["source"] == "VEHICLE_FEED" and inp["source"] == "VEHICLE_FEED":
                continue
            sim = c.get("text_similarity") or 0
            conf = 0.72 + 0.15 * (1 - c["distance_m"] / radius) + (0.1 if sim >= 55 else 0.04 if sim >= 35 else 0)
            if conf > dup_conf:
                dup, dup_conf = c["sr_id"], round(min(conf, 0.99), 2)
        return dup, dup_conf

    def use_llm(self, inp: dict, mode: str) -> bool:
        # In record/replay (free-tier quota), only the demo's citizen pothole / streetlight reports use the model;
        # rain-burst and vehicle-feed complaints run on rules in both, so a replay behaves exactly like the recording.
        if mode in ("record", "replay"):
            return inp.get("source") == "CITIZEN_WEB" and inp.get("category_chosen") in ("POTHOLE", "STREETLIGHT")
        return True

    def decision(self, out: TriageBrief) -> str:
        bits = [f"{out.priority} {out.category.replace('_', ' ').title()} -> {out.department_id}/{out.ward_id}"]
        if out.duplicate_of:
            bits.append(f"duplicate of {out.duplicate_of} ({out.duplicate_confidence:.2f})")
        if out.repeat_failure:
            bits.append("repeat failure")
        if out.interagency_referral:
            bits.append(f"refer {out.interagency_referral.agency}")
        if out.vehicle_corroboration:
            bits.append(f"{out.vehicle_corroboration} vehicles")
        return "; ".join(bits)

    # ------------------------------------------------------------------ rule-based fallback
    def fallback(self, ctx: ToolContext, inp: dict) -> TriageBrief:
        lat, lon, cat = inp["lat"], inp["lon"], inp["category_chosen"]
        why: list[str] = []
        ward = ctx.call("get_ward_for_location", {"lat": lat, "lon": lon}, by="rules")
        dept = CATEGORY_DEPARTMENT.get(cat, "ROADS")
        prio = DEFAULT_PRIORITY.get(cat, "P3")
        bumps: list[str] = []
        if inp.get("emergency_keywords_found"):
            prio = "P1"
            why.append("Emergency keywords in the description (danger to life): P1 and Control Room alerted.")

        places = ctx.call("get_sensitive_places_nearby", {"lat": lat, "lon": lon, "radius_m": 150}, by="rules")
        near = [p for p in places if p["type"] in SENSITIVE_TYPES]
        if near:
            bumps.append(f"{near[0]['distance_m']} m from {near[0]['name']}")
        road = ctx.call("get_road_class", {"lat": lat, "lon": lon}, by="rules")
        if cat in ("POTHOLE", "DAMAGED_ROAD") and road.get("road_class") == "ARTERIAL":
            bumps.append(f"on arterial road ({road['road']})")

        asset_id = None
        repeat, repeat_note, referral = False, None, None
        if cat in ASSET_TYPE_FOR:
            assets = ctx.call("find_nearby_assets", {"lat": lat, "lon": lon, "type": ASSET_TYPE_FOR[cat],
                                                     "radius_m": 40}, by="rules")
            if assets:
                a = assets[0]
                asset_id = a["asset_id"]
                hist = ctx.call("get_asset_history", {"asset_id": asset_id, "days": 60}, by="rules")
                if hist.get("repairs_in_window", 0) >= 2:
                    repeat = True
                    ago = [e["days_ago"] for e in hist["events"] if e["type"] == "REPAIR"]
                    repeat_note = f"{asset_id} repaired {len(ago)} times in 60 days ({', '.join(map(str, ago))} days ago)."
                    why.append(f"Repeat failure: {repeat_note}")
                if a["owner"] in ("BESCOM", "BWSSB"):
                    reason = f"Asset {asset_id} is maintained by {a['owner']}"
                    if a.get("feeder"):
                        reason += f" (feeder {a['feeder']})"
                    referral = {"agency": a["owner"], "reason": reason}
        if cat == "WATER_LEAK" and referral is None:
            referral = {"agency": "BWSSB", "reason": "Drinking-water pipelines are maintained by BWSSB."}

        nearby_same = ctx.call("find_nearby_open_complaints", {"lat": lat, "lon": lon, "category": cat,
                                                              "radius_m": 150 if cat == "STREETLIGHT" else DUPLICATE_RADIUS_M.get(cat, 50) * 2,
                                                              "hours": 24 * 14, "text": inp["description"]}, by="rules")
        if cat == "STREETLIGHT":
            cluster = [c for c in nearby_same if c["distance_m"] <= 150]
            if len(cluster) >= 2 or (repeat and cluster):
                n = len(cluster)
                why.append(f"{n} more open streetlight complaint{'s' if n != 1 else ''} within 150 m "
                           f"({', '.join(c['sr_id'] for c in cluster[:3])}): likely a supply/feeder fault, not one fitting.")
                if referral:
                    referral["reason"] += f"; {len(cluster) + 1} lights out on the same stretch, repeat failures: likely feeder fault"
        dup, dup_conf = self.rule_duplicate(nearby_same, inp)
        if dup:
            why.append(f"Same {cat.lower().replace('_', ' ')} reported in {dup} nearby within {DUPLICATE_WINDOW_HOURS} h "
                       f"(confidence {dup_conf:.2f}{', will be linked' if dup_conf >= MERGE_THRESHOLD else ', suggestion only'}).")

        veh = {"distinct_vehicles": 0}
        if cat in ("POTHOLE", "DAMAGED_ROAD"):
            veh = ctx.call("get_vehicle_detections_nearby", {"lat": lat, "lon": lon, "radius_m": 30, "days": 14}, by="rules")
            if veh.get("distinct_vehicles", 0) >= 3:
                bumps.append(f"confirmed by {veh['distinct_vehicles']} connected vehicles")
        works = ctx.call("get_planned_works", {"lat": lat, "lon": lon, "radius_m": 60}, by="rules")
        conflict = None
        if works:
            w = works[0]
            conflict = f"{w['name']} ({w['agency']}, until {w['end']})"
            why.append(f"Planned work nearby: {conflict}; coordinate before repair.")

        if prio != "P1" and bumps:
            prio = PRIORITIES[max(1, PRIORITIES.index(prio) - 1)]  # one level up, never to P1 by rule
            why.insert(0 if not inp.get("emergency_keywords_found") else 1,
                       f"Priority {prio}: " + "; ".join(bumps) + ".")
        pol = ctx.call("get_sla_policy", {"category": cat, "priority": prio}, by="rules")
        why.append(f"Routed to {dept} in {ward.get('ward_id')} {ward.get('ward_name', '')}; "
                   f"resolve within {pol['resolution_days']:g} days ({prio}).")
        note(ctx, "triage_tables", {"department": dept, "priority": prio, "bumps": bumps})
        officer = (ward.get("ward_officer") or {}).get("id")
        lbl = CATEGORY_LABELS.get(cat, (cat,))[0]
        summary = f"System analysis: {lbl.lower()} in {ward.get('ward_name', 'your ward')}, sent to {dept.title()} department as {prio}."
        if referral:
            summary += f" Needs action by {referral['agency']}; a referral is being prepared."
        return TriageBrief(category=cat, priority=prio, department_id=dept, ward_id=ward.get("ward_id"),
                           suggested_officer_id=officer, asset_id=asset_id, duplicate_of=dup,
                           duplicate_confidence=dup_conf, repeat_failure=repeat, repeat_failure_note=repeat_note,
                           planned_work_conflict=conflict, interagency_referral=referral,
                           vehicle_corroboration=veh.get("distinct_vehicles", 0) or 0,
                           rationale=why[:6] or ["Routed by category and location."], citizen_summary=summary,
                           confidence=0.8)

    # ------------------------------------------------------------------ deterministic side effects
    def apply(self, ctx: ToolContext, inp: dict, out: TriageBrief) -> None:
        from app.modules.complaints.merge import merge_into
        from app.modules.referrals.service import draft_referral

        db = ctx.db
        sr = db.get(ServiceRequest, inp["subject_id"])
        if sr is None or sr.status not in ("SUBMITTED", "REOPENED"):
            note(ctx, "apply_skipped", {"reason": f"status is {sr.status if sr else 'missing'}; an officer already acted"})
            return
        before = {"category": sr.category, "priority": sr.priority, "department_id": sr.department_id, "asset_id": sr.asset_id}
        # The ward always comes from the point-in-polygon lookup; the model cannot move a complaint across wards.
        if out.ward_id and out.ward_id != sr.ward_id:
            note(ctx, "ward_mismatch_ignored", {"model_ward": out.ward_id, "polygon_ward": sr.ward_id})
        if out.category != sr.category:
            sr.category = out.category
        if db.get(Department, out.department_id):
            sr.department_id = out.department_id
        if sr.emergency:
            sr.priority = "P1"  # danger to life stays P1 whatever the analysis says
        elif out.priority == "P1" and not is_emergency(sr.description):
            note(ctx, "p1_capped", {"reason": "P1 is reserved for danger to life (emergency keywords); set to P2"})
            out.priority = sr.priority = "P2"
        else:
            sr.priority = out.priority
        if out.asset_id:
            from app.models import Asset

            if db.get(Asset, out.asset_id):
                sr.asset_id = out.asset_id
        if out.suggested_officer_id and db.get(User, out.suggested_officer_id):
            u = db.get(User, out.suggested_officer_id)
            if u.role == "WARD_OFFICER" and u.ward_id == sr.ward_id:
                sr.owner_id = u.id
        if out.vehicle_corroboration:
            sr.corroboration_count = max(sr.corroboration_count or 0, out.vehicle_corroboration)
        apply_sla(db, sr)  # due date from the ORIGINAL start; never restarts
        after = {"category": sr.category, "priority": sr.priority, "department_id": sr.department_id, "asset_id": sr.asset_id}
        if after != before:
            db.add(AuditLog(actor=ctx.actor.id, action="SR.system_analysis", object=f"SR:{sr.id}",
                            before_json=before, after_json={**after, "reason": "System Analysis", "run_id": ctx.run_id},
                            at=now()))

        if out.interagency_referral and sr.status == "SUBMITTED":
            draft_referral(db, sr, out.interagency_referral.agency, out.interagency_referral.reason, ctx.run_id)

        merged = False
        if sr.status == "SUBMITTED":
            radius = DUPLICATE_RADIUS_M.get(sr.category, 50)
            lat, lon = geo.latlon(sr.location)
            nearby = ctx.call("find_nearby_open_complaints", {"lat": lat, "lon": lon, "category": sr.category,
                                                              "radius_m": radius * 2, "hours": DUPLICATE_WINDOW_HOURS,
                                                              "text": sr.description}, by="rules")
            rule_dup, rule_conf = self.rule_duplicate(nearby, {**inp, "category_chosen": sr.category})
            model_dup = out.duplicate_of
            if model_dup and model_dup not in {c["sr_id"] for c in nearby}:
                note(ctx, "duplicate_rejected", {"duplicate_of": model_dup, "reason": "not an open complaint within the duplicate radius"})
                model_dup = None
            # brief 5.2: auto-merge at >= 0.9; the radius/time/text rule decides, the model can only add agreement
            if rule_dup:
                conf = max(rule_conf, out.duplicate_confidence if model_dup == rule_dup else 0.0)
                out.duplicate_of, out.duplicate_confidence = rule_dup, round(conf, 2)
            elif model_dup:
                out.duplicate_of = model_dup
                out.duplicate_confidence = min(out.duplicate_confidence, 0.89)  # suggestion only: rule did not confirm
            else:
                out.duplicate_of, out.duplicate_confidence = None, 0.0
            parent = db.get(ServiceRequest, out.duplicate_of) if out.duplicate_of else None
            if (parent is not None and out.duplicate_confidence >= MERGE_THRESHOLD and parent.id != sr.id
                    and parent.category == sr.category and parent.status not in ("CLOSED", "REJECTED", "MERGED")):
                merge_into(db, sr, parent, ctx.actor, confidence=out.duplicate_confidence,
                           note=f"System Analysis: same issue as {parent.id} (confidence {out.duplicate_confidence:.2f})")
                merged = True
        if not merged:
            db.add(Timeline(sr_id=sr.id, stage="System Analysis",
                            remarks=out.citizen_summary or "Your grievance has been examined and routed to the right department.",
                            remarks_kn=f"ವ್ಯವಸ್ಥೆಯ ವಿಶ್ಲೇಷಣೆ: ನಿಮ್ಮ ದೂರನ್ನು ಸಂಬಂಧಿತ ವಿಭಾಗಕ್ಕೆ ({sr.department_id}) ಆದ್ಯತೆ {sr.priority} ರಂದು ಕಳುಹಿಸಲಾಗಿದೆ.",
                            actor_type="AGENT", at=now()))
            if sr.status == "SUBMITTED":
                notify_citizen(db, sr, "ACK")
        if sr.emergency:
            from app.modules.notifications.service import notify_staff

            for u in db.scalars(select(User).where(User.role == "CONTROL_ROOM")):
                notify_staff(db, u.id, "P1_ALERT", f"P1 emergency {sr.id}: {sr.description[:120]}", sr.id, "CONTROL")


investigator = CaseInvestigator()
