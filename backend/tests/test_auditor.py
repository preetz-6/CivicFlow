"""Evidence Auditor: every check (old photo, far GPS, reused hash, missing EXIF) + fallback + model overrides."""
import json
from datetime import timedelta

import pytest
from sqlalchemy import select

from app.adapters.llm import LLMResult
from app.agents.auditor import auditor
from app.agents.runtime import registry
from app.agents.runtime.loop import run_agent
from app.core.actor import Actor
from app.core.clock import clock
from app.core.db import SessionLocal
from app.models import AgentRun, Crew, Notification, ServiceRequest, WorkOrder
from app.modules import geo
from app.modules.media.service import store_photo
from app.modules.system import demo_photos
from app.modules.workflow.service import transition
from tests.factories import make_sr, make_wo


@pytest.fixture
def job(db, world):
    """SR (IN_PROGRESS) + WO started 1 h after assignment, with a before-photo."""
    sr = make_sr(db, world, status="IN_PROGRESS")
    wo = make_wo(db, world, sr, status="ASSIGNED")
    site = geo.latlon(sr.location)
    store_photo(db, demo_photos.make("before", wo_id=wo.id, category="POTHOLE", site=site, assigned_at=wo.assigned_at),
                "image/jpeg", kind="BEFORE", uploaded_by=world.field12.id, sr_id=sr.id, wo_id=wo.id)
    clock.advance(timedelta(hours=1))
    transition(db, wo, "IN_PROGRESS", Actor.from_user(world.field12))
    db.commit()
    return db, world, sr, wo, site


def complete_with(job, variant, run=True):
    db, world, sr, wo, site = job
    clock.advance(timedelta(hours=2))
    reuse = None
    data = demo_photos.make(variant, wo_id=wo.id, category="POTHOLE", site=site, assigned_at=wo.assigned_at,
                            reuse_bytes=reuse)
    store_photo(db, data, "image/jpeg", kind="AFTER", uploaded_by=world.field12.id, sr_id=sr.id, wo_id=wo.id)
    if run:
        registry.register_agents()
    transition(db, wo, "COMPLETED", Actor.from_user(world.field12))
    db.commit()  # -> work_order.completed -> auditor (bus.sync)
    db.expire_all()
    return db.get(WorkOrder, wo.id), db.scalar(select(AgentRun).where(AgentRun.agent == "auditor").order_by(AgentRun.id.desc()))


def checks(run):
    return {c["name"]: c for c in run.output["checks"]}


def test_good_photo_passes_and_waits_for_human(job):
    wo, run = complete_with(job, "after_good")
    assert run.status == "FALLBACK" and run.output["verdict"] == "PASS"
    assert wo.status == "COMPLETED" and wo.audit_verdict == "PASS" and wo.audit_run_id == run.id
    c = checks(run)
    assert c["Photo location matches site"]["passed"] is True and c["Not a reused photo"]["passed"] is True
    assert c["Work visibly done (photo check)"]["passed"] is None  # vision skipped in rules mode


def test_far_gps_fails_and_sends_to_rework(job):
    db = job[0]
    wo, run = complete_with(job, "after_far")
    assert run.output["verdict"] == "FAIL" and run.output["hard_evidence"] is True
    assert "2.1 km from complaint site (limit 50 m)" in checks(run)["Photo location matches site"]["detail"]
    assert wo.status == "REWORK" and "2.1 km" in wo.rework_reason
    assert db.get(ServiceRequest, wo.sr_id).status == "IN_PROGRESS"
    assert db.scalar(select(Notification).where(Notification.event == "WO_REWORK"))


def test_photo_taken_before_assignment_fails(job):
    wo, run = complete_with(job, "after_old")
    assert run.output["verdict"] == "FAIL" and checks(run)["Photo taken after assignment"]["passed"] is False
    assert wo.status == "REWORK"


def test_missing_exif_is_unverifiable_not_fail(job):
    wo, run = complete_with(job, "after_noexif")
    assert run.output["verdict"] == "FLAG"
    assert checks(run)["Photo location matches site"]["passed"] is None
    assert wo.status == "COMPLETED"  # a human decides


def test_reused_photo_fails(job):
    db, world, sr, wo, site = job
    # crew re-uploads the job's own BEFORE photo as the AFTER photo
    clock.advance(timedelta(hours=2))
    before = demo_photos.make("before", wo_id=wo.id, category="POTHOLE", site=site, assigned_at=wo.assigned_at)
    store_photo(db, before, "image/jpeg", kind="AFTER", uploaded_by=world.field12.id, sr_id=sr.id, wo_id=wo.id)
    registry.register_agents()
    transition(db, wo, "COMPLETED", Actor.from_user(world.field12))
    db.commit()
    db.expire_all()
    run = db.scalar(select(AgentRun).where(AgentRun.agent == "auditor"))
    assert run.output["verdict"] == "FAIL" and checks(run)["Not a reused photo"]["passed"] is False
    assert "BEFORE photo" in checks(run)["Not a reused photo"]["detail"]


def test_rework_then_good_photo_passes_and_old_photo_not_reusable(job):
    db, world, sr, wo, site = job
    wo, run = complete_with(job, "after_far")
    assert wo.status == "REWORK"
    clock.advance(timedelta(minutes=30))
    transition(db, wo, "IN_PROGRESS", Actor.from_user(world.field12))
    db.commit()
    from app.core.errors import MissingFields

    with pytest.raises(MissingFields):  # the far photo from the first attempt does not count any more
        transition(db, wo, "COMPLETED", Actor.from_user(world.field12))
    db.rollback()
    wo, run = complete_with(job, "after_good")
    assert run.output["verdict"] == "PASS" and wo.status == "COMPLETED"


def test_repeated_flags_raise_crew_audit_priority(job, db, world):
    complete_with(job, "after_noexif")
    sr2 = make_sr(db, world, status="IN_PROGRESS")
    wo2 = make_wo(db, world, sr2, status="IN_PROGRESS", started_at=clock.now())
    db.commit()
    complete_with((db, world, sr2, wo2, geo.latlon(sr2.location)), "after_noexif")
    assert db.get(Crew, "W12-A").audit_priority == "HIGH"


# ---------------------------------------------------------------------------- LLM path
class FakeLLM:
    def __init__(self, script):
        self.script = list(script)

    def available(self):
        return True

    def create(self, **kw):
        x = self.script.pop(0)
        if isinstance(x, Exception):
            raise x
        return x


def final(obj):
    return LLMResult([{"type": "text", "text": json.dumps(obj)}], "end_turn", "claude-test", "live")


def verdict(v, hard=False):
    return {"verdict": v, "score": 90 if v == "PASS" else 30, "hard_evidence": hard, "confidence": 0.8,
            "checks": [{"name": "Work visibly done (photo check)", "passed": v == "PASS", "detail": "model view"}],
            "rationale": ["model says so"]}


def _complete_no_agent(job, variant):
    from app.core.bus import bus

    bus.enabled = False
    try:
        wo, _ = complete_with(job, variant, run=False)
    finally:
        bus.enabled = True
    return wo


def _run(monkeypatch, wo, script):
    monkeypatch.setattr("app.agents.runtime.loop.llm", FakeLLM(script))
    rid = run_agent(auditor, "work_order.completed", {"id": wo.id})
    s = SessionLocal()
    r, w = s.get(AgentRun, rid), s.get(WorkOrder, wo.id)
    out = (r.status, r.model, r.output["verdict"], w.status)
    s.close()
    return out


def test_model_cannot_pass_a_far_photo(job, monkeypatch):
    wo = _complete_no_agent(job, "after_far")
    assert _run(monkeypatch, wo, [final(verdict("PASS"))]) == ("OK", "claude-test", "FAIL", "REWORK")


def test_model_fail_without_hard_evidence_becomes_flag(job, monkeypatch):
    wo = _complete_no_agent(job, "after_good")
    assert _run(monkeypatch, wo, [final(verdict("FAIL"))]) == ("OK", "claude-test", "FLAG", "COMPLETED")


def test_auditor_falls_back_when_llm_errors(job, monkeypatch):
    wo = _complete_no_agent(job, "after_far")
    assert _run(monkeypatch, wo, [RuntimeError("boom")]) == ("FALLBACK", "rules", "FAIL", "REWORK")


def test_citizen_sees_only_the_approved_after_photo(job):
    from app.modules.complaints.serialize import track_view

    db, world, sr, wo, site = job
    wo, _ = complete_with(job, "after_far")
    clock.advance(timedelta(minutes=30))
    transition(db, wo, "IN_PROGRESS", Actor.from_user(world.field12))
    db.commit()
    wo, run = complete_with(job, "after_good")
    transition(db, wo, "VERIFIED", Actor.from_user(world.control))
    db.commit()
    tv = track_view(db, db.get(ServiceRequest, sr.id))
    assert len(tv["after_photos"]) == 1
    assert abs(tv["after_photos"][0]["exif_lat"] - site[0]) < 0.001  # the on-site photo, not the 2 km one
    assert "IST" in checks(run)["Photo taken after assignment"]["detail"]
