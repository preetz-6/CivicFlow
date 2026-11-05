"""Agent 4: Evidence Auditor. Trigger: work_order.completed.

Decides whether the completion evidence is believable BEFORE a human approves.
Hard checks (time, GPS, reuse, EXIF presence) are computed by deterministic code on both paths; the
model adds the visual judgement and the write-up. Automatic action is limited to FAIL-with-hard-evidence
-> REWORK. PASS and FLAG always wait for a human Approve.
"""
from __future__ import annotations

from datetime import timedelta
from typing import Literal

import imagehash
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select

from app.agents import vision
from app.agents.runtime.base import Agent
from app.agents.runtime.tools import ToolContext, note, props, tool
from app.core.clock import IST, now
from app.domain_config import AUDIT_RADIUS_DEFAULT_M, AUDIT_RADIUS_M
from app.models import AgentRun, Attachment, Crew, ServiceRequest, User, WorkOrder
from app.modules import geo
from app.modules.notifications.service import notify_staff

HARD_GPS_M = 500  # further than this is clear evidence, not a judgement call
REUSE_HAMMING = 6  # pHash distance <= this means "the same photo"


class Check(BaseModel):
    name: str
    passed: bool | None = Field(description="true / false / null when it cannot be verified")
    detail: str


class AuditVerdict(BaseModel):
    verdict: Literal["PASS", "FLAG", "FAIL"]
    score: int = Field(ge=0, le=100)
    checks: list[Check]
    rationale: list[str] = Field(min_length=1, max_length=6)
    confidence: float = Field(ge=0, le=1)
    hard_evidence: bool = Field(False, description="FAIL is backed by a hard check (GPS far away, reused photo, taken before assignment)")


# ----------------------------------------------------------------------------- tools
def _site(db, wo: WorkOrder):
    sr = db.get(ServiceRequest, wo.sr_id)
    return sr, geo.latlon(sr.location)


@tool("get_work_order", "Work order details: site location, category, assignment/start times, crew, photo ids.",
      {"properties": props(wo_id="string"), "required": ["wo_id"]})
def get_work_order(ctx, wo_id: str):
    wo = ctx.db.get(WorkOrder, wo_id)
    if wo is None:
        return {"error": f"no work order {wo_id}"}
    sr, (lat, lon) = _site(ctx.db, wo)
    photos = ctx.db.scalars(select(Attachment).where(Attachment.wo_id == wo.id).order_by(Attachment.id)).all()
    return {"wo_id": wo.id, "sr_id": sr.id, "category": sr.category, "site": {"lat": lat, "lon": lon},
            "allowed_radius_m": AUDIT_RADIUS_M.get(sr.category, AUDIT_RADIUS_DEFAULT_M), "crew_id": wo.crew_id,
            "assigned_at": wo.assigned_at.isoformat(), "started_at": wo.started_at.isoformat() if wo.started_at else None,
            "completed_at": wo.completed_at.isoformat() if wo.completed_at else None, "rework_count": wo.rework_count,
            "photos": [{"attachment_id": p.id, "kind": p.kind, "uploaded_at": p.uploaded_at.isoformat()} for p in photos]
                      + [{"attachment_id": p.id, "kind": "CITIZEN"} for p in ctx.db.scalars(
                          select(Attachment).where(Attachment.sr_id == sr.id, Attachment.kind == "CITIZEN"))]}


@tool("get_photo_metadata", "EXIF capture time and GPS of a photo, plus upload time.",
      {"properties": props(attachment_id="integer"), "required": ["attachment_id"]})
def get_photo_metadata(ctx, attachment_id: int):
    a = ctx.db.get(Attachment, attachment_id)
    if a is None:
        return {"error": f"no attachment {attachment_id}"}
    return {"attachment_id": a.id, "kind": a.kind, "exif_time": a.exif_time.isoformat() if a.exif_time else None,
            "exif_lat": a.exif_lat, "exif_lon": a.exif_lon, "uploaded_at": a.uploaded_at.isoformat(),
            "has_exif_time": a.exif_time is not None, "has_exif_gps": a.exif_lat is not None}


@tool("distance_m", "Distance in metres between two lat/lon points.",
      {"properties": props(lat1="number", lon1="number", lat2="number", lon2="number"),
       "required": ["lat1", "lon1", "lat2", "lon2"]})
def distance_m(ctx, lat1: float, lon1: float, lat2: float, lon2: float):
    return {"distance_m": round(geo.distance_m((lat1, lon1), (lat2, lon2)), 1)}


def _hamming(a: str, b: str) -> int:
    return imagehash.hex_to_hash(a) - imagehash.hex_to_hash(b)


@tool("compare_with_all_photos",
      "Perceptual-hash comparison of a photo against every other stored photo (this job's before-photo and all "
      "other jobs). Hamming distance 0-6 means effectively the same picture.",
      {"properties": props(attachment_id="integer"), "required": ["attachment_id"]})
def compare_with_all_photos(ctx, attachment_id: int):
    a = ctx.db.get(Attachment, attachment_id)
    if a is None:
        return {"error": f"no attachment {attachment_id}"}
    others = ctx.db.scalars(select(Attachment).where(Attachment.id != a.id, or_(Attachment.phash.is_not(None),
                                                                                Attachment.sha256 == a.sha256))).all()
    matches = []
    for o in others:
        exact = o.sha256 == a.sha256
        d = 0 if exact else (_hamming(a.phash, o.phash) if a.phash and o.phash else 64)
        if d <= 12:
            matches.append({"attachment_id": o.id, "kind": o.kind, "wo_id": o.wo_id, "sr_id": o.sr_id,
                            "hamming": d, "identical_file": exact, "same_job": o.wo_id == a.wo_id})
    matches.sort(key=lambda m: m["hamming"])
    return {"compared": len(others), "closest": matches[:5],
            "reused": any(m["hamming"] <= REUSE_HAMMING for m in matches)}


@tool("vision_compare",
      "Look at the before and after photos: is the issue visibly fixed, and is it the same place? "
      "Returns {fixed, same_scene, notes} or {skipped}.",
      {"properties": props(before_id="integer", after_id="integer", category="string"),
       "required": ["after_id", "category"]})
def vision_compare(ctx, after_id: int, category: str, before_id: int | None = None):
    after = ctx.db.get(Attachment, after_id)
    before = ctx.db.get(Attachment, before_id) if before_id else None
    if after is None:
        return {"error": f"no attachment {after_id}"}
    imgs = [before, after] if before else [after]
    return vision.ask_vision("vision_compare", imgs, (
        f"Category: {category}. " + ("Image 1 is BEFORE the repair, image 2 is AFTER. " if before else "This is the AFTER photo. ") +
        'Reply {"fixed": true|false|null, "same_scene": true|false|null, "notes": "<one sentence>"}'))


@tool("get_crew_audit_history", "Recent audit verdicts for a crew (last 30 days).",
      {"properties": props(crew_id="string"), "required": ["crew_id"]})
def get_crew_audit_history(ctx, crew_id: str):
    since = now() - timedelta(days=30)
    rows = ctx.db.execute(select(WorkOrder.audit_verdict, func.count()).where(
        WorkOrder.crew_id == crew_id, WorkOrder.completed_at >= since, WorkOrder.audit_verdict.is_not(None))
        .group_by(WorkOrder.audit_verdict)).all()
    crew = ctx.db.get(Crew, crew_id)
    return {"crew_id": crew_id, "audit_priority": crew.audit_priority if crew else None, "last_30_days": dict(rows)}


# ----------------------------------------------------------------------------- deterministic checks
def hard_checks(ctx: ToolContext, wo: WorkOrder, after: Attachment, *, by: str) -> tuple[list[Check], dict]:
    """The facts. Run via tools so they appear as steps in the Activity Log."""
    info = ctx.call("get_work_order", {"wo_id": wo.id}, by=by)
    meta = ctx.call("get_photo_metadata", {"attachment_id": after.id}, by=by)
    checks: list[Check] = []
    facts = {"far": False, "reused": False, "before_assignment": False, "unverifiable": False}

    if meta["exif_time"] is None:
        checks.append(Check(name="Photo taken after assignment", passed=None,
                            detail="No capture time in the photo (EXIF missing): cannot verify. Needs a human look."))
        facts["unverifiable"] = True
    elif after.exif_time < wo.assigned_at - timedelta(minutes=2):  # EXIF has whole-second precision
        hours = (wo.assigned_at - after.exif_time).total_seconds() / 3600
        checks.append(Check(name="Photo taken after assignment", passed=False,
                            detail=f"Photo was taken {hours:.0f} h BEFORE the job was assigned ({after.exif_time.astimezone(IST):%d %b %H:%M} IST)."))
        facts["before_assignment"] = True
    elif after.exif_time > after.uploaded_at + timedelta(minutes=10):
        checks.append(Check(name="Photo taken after assignment", passed=False,
                            detail="Photo capture time is later than its upload time: clock tampering suspected."))
    else:
        checks.append(Check(name="Photo taken after assignment", passed=True,
                            detail=f"Taken {after.exif_time.astimezone(IST):%d %b %H:%M} IST, after assignment at {wo.assigned_at.astimezone(IST):%d %b %H:%M} IST."))

    radius = info["allowed_radius_m"]
    if meta["exif_lat"] is None:
        checks.append(Check(name="Photo location matches site", passed=None,
                            detail="No GPS in the photo (EXIF missing): cannot verify the location."))
        facts["unverifiable"] = True
    else:
        d = ctx.call("distance_m", {"lat1": meta["exif_lat"], "lon1": meta["exif_lon"],
                                    "lat2": info["site"]["lat"], "lon2": info["site"]["lon"]}, by=by)["distance_m"]
        facts["distance_m"] = d
        if d <= radius:
            checks.append(Check(name="Photo location matches site", passed=True, detail=f"Taken {d:.0f} m from the complaint site (limit {radius} m)."))
        else:
            txt = f"{d / 1000:.1f} km" if d >= 1000 else f"{d:.0f} m"
            checks.append(Check(name="Photo location matches site", passed=False,
                                detail=f"Photo location {txt} from complaint site (limit {radius} m)."))
            facts["far"] = d > HARD_GPS_M

    cmp = ctx.call("compare_with_all_photos", {"attachment_id": after.id}, by=by)
    reuse = [m for m in cmp.get("closest", []) if m["hamming"] <= REUSE_HAMMING]
    if reuse:
        m = reuse[0]
        where = "this job's own BEFORE photo (nothing changed)" if m["same_job"] and m["kind"] == "BEFORE" else \
            f"a photo from {m['wo_id'] or m['sr_id']}"
        checks.append(Check(name="Not a reused photo", passed=False,
                            detail=f"Matches {where} (hash distance {m['hamming']}{', identical file' if m['identical_file'] else ''})."))
        facts["reused"] = True
    else:
        checks.append(Check(name="Not a reused photo", passed=True, detail=f"Unique among {cmp.get('compared', 0)} stored photos."))
    facts["before_id"] = next((p["attachment_id"] for p in info["photos"] if p["kind"] == "BEFORE"), None) or \
        next((p["attachment_id"] for p in info["photos"] if p["kind"] == "CITIZEN"), None)
    facts["category"] = info["category"]
    return checks, facts


def score_and_verdict(checks: list[Check], facts: dict) -> tuple[int, str, bool]:
    score = 100
    for c in checks:
        if c.passed is None and c.detail.startswith("Skipped"):
            continue  # vision not available (rules mode): neither evidence for nor against
        if c.passed is None:
            score -= 25
        elif c.passed is False:
            score -= {"Photo location matches site": 60, "Not a reused photo": 70,
                      "Photo taken after assignment": 40, "Work visibly done (photo check)": 30}.get(c.name, 30)
    score = max(0, min(100, score))
    hard = facts["far"] or facts["reused"] or facts["before_assignment"]
    if hard:
        return min(score, 20), "FAIL", True
    if any(c.passed is not True for c in checks if c.name != "Work visibly done (photo check)" or c.passed is False):
        return score, "FLAG", False
    return score, "PASS", False


SYSTEM = """You are the Evidence Auditor for CivicFlow Municipal Corporation. A field crew has marked a work order
COMPLETED and uploaded an after-photo. Decide whether the evidence is believable before an Executive Engineer approves.

Check, using the tools:
1. The after-photo was taken AFTER the job was assigned (EXIF time vs assigned_at).
2. Its GPS is within the allowed radius of the complaint site (use distance_m).
3. It is not a reused photo: compare_with_all_photos; hash distance 0-6 = same picture (including this job's own before-photo).
4. vision_compare(before, after): is the issue visibly fixed, and is it the same place?
5. Missing EXIF time/GPS = "unverifiable" (passed=null). That needs a human; it is NOT a fail on its own.

Verdict: FAIL only with hard evidence (GPS more than 500 m away, reused photo, or taken before assignment) and set
hard_evidence=true. FLAG when anything is doubtful or unverifiable. PASS only when every check passes.
Rationale: short factual bullets the Executive Engineer can act on."""


class EvidenceAuditor(Agent):
    name = "auditor"
    label = "Evidence Auditor"
    system_prompt = SYSTEM
    triggers = ["work_order.completed"]
    output_model = AuditVerdict
    subject_type = "WO"
    max_steps = 8
    timeout_s = 60.0
    tools = ["get_work_order", "get_photo_metadata", "distance_m", "compare_with_all_photos", "vision_compare",
             "get_crew_audit_history"]

    def build_input(self, db, payload):
        wo = db.get(WorkOrder, payload["id"])
        if wo is None or wo.status != "COMPLETED":
            return None
        after = latest_after(db, wo)
        if after is None:
            return None
        sr = db.get(ServiceRequest, wo.sr_id)
        far = after.exif_lat is not None and geo.distance_m((after.exif_lat, after.exif_lon), geo.latlon(sr.location)) > HARD_GPS_M
        early = after.exif_time is not None and after.exif_time < wo.assigned_at - timedelta(minutes=2)
        reused = db.scalar(select(func.count()).select_from(Attachment).where(
            Attachment.id != after.id, Attachment.sha256 == after.sha256)) > 0
        return {"subject_id": wo.id, "wo_id": wo.id, "sr_id": wo.sr_id, "crew_id": wo.crew_id,
                "after_photo_id": after.id, "rework_count": wo.rework_count, "_hard_fail": bool(far or early or reused)}

    def use_llm(self, inp: dict, mode: str) -> bool:
        # Hard evidence (far GPS, taken before assignment, identical file) already decides FAIL; the model adds nothing.
        return not inp.get("_hard_fail")

    def decision(self, out: AuditVerdict) -> str:
        failed = [c.detail.rstrip(".") for c in out.checks if c.passed is False]
        unver = [c.name.lower() for c in out.checks if c.passed is None and "photo check" not in c.name]
        tail = "; ".join(failed) if failed else (f"unverifiable: {', '.join(unver)}" if unver else "all checks passed")
        return f"{out.verdict} (score {out.score}): {tail}"

    def fallback(self, ctx, inp):
        wo = ctx.db.get(WorkOrder, inp["wo_id"])
        after = ctx.db.get(Attachment, inp["after_photo_id"])
        checks, facts = hard_checks(ctx, wo, after, by="rules")
        checks.append(Check(name="Work visibly done (photo check)", passed=None,
                            detail="Skipped: visual check needs the vision model (rules mode)."))
        score, verdict, hard = score_and_verdict(checks, facts)
        why = [c.detail for c in checks if c.passed is False] or ["Time, location and uniqueness checks passed."]
        if any(c.passed is None for c in checks[:-1]):
            why.append("Some evidence could not be verified; an Executive Engineer should look at the photo.")
        return AuditVerdict(verdict=verdict, score=score, checks=checks, rationale=why[:6],
                            confidence=0.9 if hard else 0.7, hard_evidence=hard)

    def apply(self, ctx, inp, out: AuditVerdict):
        from app.modules.workflow.service import transition

        db = ctx.db
        wo = db.get(WorkOrder, inp["wo_id"])
        after = db.get(Attachment, inp["after_photo_id"])
        # Re-run the hard checks deterministically: the model can never FAIL a crew without hard evidence,
        # and can never PASS a photo that a hard check failed.
        checks, facts = hard_checks(ctx, wo, after, by="rules")
        hard = facts["far"] or facts["reused"] or facts["before_assignment"]
        # The displayed checks are always the deterministic ones (same names, IST times) plus ONE visual check,
        # which is the only thing the model contributes.
        vis = next((c for c in out.checks if any(w in c.name.lower() for w in ("vision", "visib", "fixed", "photo check"))), None)
        vision = Check(name="Work visibly done (photo check)",
                       passed=vis.passed if vis else None,
                       detail=(vis.detail if vis else "Not assessed by the vision model."))
        all_checks = checks + [vision]
        score, rule_verdict, _ = score_and_verdict(all_checks, facts)
        if hard:
            verdict = "FAIL"
        elif rule_verdict == "FLAG" or out.verdict != "PASS":
            verdict = "FLAG"  # the model can never FAIL a crew without hard evidence
            if out.verdict == "FAIL":
                note(ctx, "fail_downgraded", {"reason": "no hard evidence; a human decides"})
        else:
            verdict = "PASS"
        if out.verdict == "PASS" and verdict != "PASS":
            note(ctx, "pass_downgraded", {"reason": "a deterministic or visual check did not pass"})
        out.checks, out.verdict, out.hard_evidence = all_checks, verdict, hard
        out.score = min(out.score, score) if not hard else min(score, 20)
        wo.audit_verdict, wo.audit_score, wo.audit_run_id = verdict, out.score, ctx.run_id
        if verdict == "FAIL" and wo.status == "COMPLETED":
            reason = "Auto-check failed: " + "; ".join(c.detail for c in checks if c.passed is False)  # hard checks only
            transition(db, wo, "REWORK", ctx.actor, rework_reason=reason[:900])
            for u in db.scalars(select(User).where(User.crew_id == wo.crew_id)):
                notify_staff(db, u.id, "WO_REWORK", f"{wo.id} sent back for rework. {reason[:300]}", wo.sr_id, "FIELD",
                             dedupe=f"{ctx.run_id}")
        recent = db.scalar(select(func.count()).select_from(WorkOrder).where(
            WorkOrder.crew_id == wo.crew_id, WorkOrder.audit_verdict.in_(["FLAG", "FAIL"]),
            WorkOrder.completed_at >= now() - timedelta(days=30)))
        crew = db.get(Crew, wo.crew_id)
        if crew and (recent or 0) >= 2 and crew.audit_priority != "HIGH":
            crew.audit_priority = "HIGH"
            note(ctx, "crew_audit_priority", {"crew": crew.id, "flags_or_fails_30d": recent, "audit_priority": "HIGH"})


def latest_after(db, wo: WorkOrder) -> Attachment | None:
    q = select(Attachment).where(Attachment.wo_id == wo.id, Attachment.kind == "AFTER")
    if wo.started_at:
        q = q.where(Attachment.uploaded_at >= wo.started_at)
    return db.scalar(q.order_by(Attachment.id.desc()).limit(1))


auditor = EvidenceAuditor()


def last_audit(db, wo_id: str) -> AgentRun | None:
    return db.scalar(select(AgentRun).where(AgentRun.agent == "auditor", AgentRun.subject_id == wo_id).order_by(AgentRun.id.desc()))
