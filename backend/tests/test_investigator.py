"""Agent runtime + Case Investigator, on the real demo seed."""
import json

import pytest
from sqlalchemy import select

from app.adapters import llm as llm_mod
from app.adapters.llm import CacheMiss, LLMResult
from app.agents.runtime import registry
from app.agents.runtime.loop import run_agent
from app.core.db import SessionLocal
from app.models import AgentRun, AgentStep, Notification, Referral, ServiceRequest, Timeline
from app.modules.complaints.service import create_complaint
from app.seed import build, geo


@pytest.fixture
def seeded(db):
    build.rng.seed(2026)
    build.Seeder(db).run()
    db.commit()
    registry.register_agents()
    return db


def get_run(rid) -> AgentRun:
    s = SessionLocal()
    try:
        r = s.get(AgentRun, rid)
        s.expunge(r)
        return r
    finally:
        s.close()


def lodge(db, cat, lat, lon, desc, phone="9811111111", lang="en"):
    sr = create_complaint(db, category=cat, description=desc, lat=lat, lon=lon, contact_phone=phone, language=lang)
    db.commit()  # -> complaint.submitted -> investigator runs inline (bus.sync)
    db.expire_all()
    return db.get(ServiceRequest, sr.id)


def last_run(db, sr_id) -> AgentRun:
    return db.scalar(select(AgentRun).where(AgentRun.subject_id == sr_id).order_by(AgentRun.id.desc()))


def test_school_pothole_rules_brief(seeded):
    db = seeded
    sr = lodge(db, "POTHOLE", *geo.POTHOLE_SCHOOL, "Big pothole in front of the school gate, children walk around it", lang="kn")
    run = last_run(db, sr.id)
    assert run.status == "FALLBACK" and run.model == "rules"
    assert sr.priority == "P2" and sr.department_id == "ROADS" and sr.ward_id == "W12"
    assert "Govt. Higher Primary School" in run.rationale
    steps = db.scalars(select(AgentStep.tool).where(AgentStep.run_id == run.id)).all()
    assert "rule:get_sensitive_places_nearby" in steps and "rule:get_ward_for_location" in steps
    assert db.scalar(select(Notification).where(Notification.related_sr_id == sr.id, Notification.event == "ACK")).language == "kn"
    assert any(t.stage == "System Analysis" for t in db.scalars(select(Timeline).where(Timeline.sr_id == sr.id)))


def test_duplicates_auto_merge(seeded):
    db = seeded
    first = lodge(db, "POTHOLE", *geo.POTHOLE_SCHOOL, "Big pothole in front of the school gate, children at risk", phone="9811111111")
    second = lodge(db, "POTHOLE", geo.POTHOLE_SCHOOL[0] + 0.00003, geo.POTHOLE_SCHOOL[1], "Huge pothole near the school gate", phone="9822222222")
    third = lodge(db, "POTHOLE", geo.POTHOLE_SCHOOL[0], geo.POTHOLE_SCHOOL[1] + 0.00004, "pothole at school gate, kids at risk", phone="9833333333")
    db.refresh(first)
    assert second.status == "MERGED" and third.status == "MERGED"
    assert second.parent_sr_id == first.id and third.parent_sr_id == first.id
    assert first.reporter_count == 3 and first.priority == "P2"
    assert last_run(db, second.id).output["duplicate_confidence"] >= 0.9
    # every merged reporter is told, and will keep getting the parent's updates
    assert db.scalar(select(Notification).where(Notification.related_sr_id == second.id, Notification.event == "MERGED"))
    tl = [t.remarks for t in db.scalars(select(Timeline).where(Timeline.sr_id == first.id))]
    assert any("linked 2 similar reports" in r for r in tl)


def test_far_or_different_category_is_not_merged(seeded):
    db = seeded
    lodge(db, "POTHOLE", *geo.POTHOLE_SCHOOL, "Big pothole in front of the school gate")
    far = lodge(db, "POTHOLE", geo.POTHOLE_SCHOOL[0] + 0.0006, geo.POTHOLE_SCHOOL[1], "Big pothole near the school")  # ~65 m
    other = lodge(db, "GARBAGE", *geo.POTHOLE_SCHOOL, "Garbage dumped at the school gate")
    assert far.status == "SUBMITTED" and other.status == "SUBMITTED"


def test_streetlight_repeat_failure_bescom(seeded):
    db = seeded
    sr = lodge(db, "STREETLIGHT", *geo.STREETLIGHT_DEMO_SR, "Streetlight not working at the bus stand, very dark at night")
    out = last_run(db, sr.id).output
    assert out["asset_id"] == "STREETLIGHT-W12-00871"
    assert out["repeat_failure"] is True
    assert out["interagency_referral"]["agency"] == "BESCOM"
    assert "feeder" in out["interagency_referral"]["reason"]
    assert sr.priority == "P2" and "Kengeri TTMC Bus Stand" in " ".join(out["rationale"])
    assert "2 more open streetlight complaints within 150 m" in " ".join(out["rationale"])
    ref = db.scalar(select(Referral).where(Referral.sr_id == sr.id))
    assert ref.status == "DRAFT"  # sent only when the officer accepts


def test_emergency_is_p1(seeded):
    db = seeded
    sr = lodge(db, "OPEN_MANHOLE", 12.9150, 77.4880, "Open manhole on the footpath, a child fell in this morning")
    assert sr.priority == "P1"
    assert db.scalar(select(Notification).where(Notification.related_sr_id == sr.id, Notification.event == "P1_ALERT"))


# ----------------------------------------------------------------------------- LLM path (scripted fake)
class FakeLLM:
    def __init__(self, script):
        self.script, self.calls = list(script), []

    def available(self):
        return True

    def create(self, **kw):
        self.calls.append(kw)
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def tool_use(name, args, id_="t1"):
    return LLMResult([{"type": "tool_use", "id": id_, "name": name, "input": args}], "tool_use", "claude-test", "live")


def final(obj):
    return LLMResult([{"type": "text", "text": json.dumps(obj)}], "end_turn", "claude-test", "live")


BRIEF = {"category": "POTHOLE", "priority": "P2", "department_id": "ROADS", "ward_id": "W12", "duplicate_confidence": 0,
         "rationale": ["School 40 m away", "No duplicates"], "confidence": 0.86}


def make_sr(db):
    from app.core.bus import bus

    bus.enabled = False
    try:
        sr = lodge(db, "POTHOLE", *geo.POTHOLE_SCHOOL, "Pothole in front of the school gate")
    finally:
        bus.enabled = True
    return sr


def test_llm_loop_tools_and_validated_output(seeded, monkeypatch):
    db = seeded
    sr = make_sr(db)
    fake = FakeLLM([tool_use("get_sensitive_places_nearby", {"lat": geo.POTHOLE_SCHOOL[0], "lon": geo.POTHOLE_SCHOOL[1]}),
                    final(BRIEF)])
    monkeypatch.setattr("app.agents.runtime.loop.llm", fake)
    from app.agents.investigator import investigator

    rid = run_agent(investigator, "complaint.submitted", {"id": sr.id})
    s = SessionLocal()
    run = s.get(AgentRun, rid)
    assert run.status == "OK" and run.model == "claude-test" and run.confidence == 0.86
    steps = s.scalars(select(AgentStep).where(AgentStep.run_id == rid)).all()
    assert [st.tool for st in steps if not st.tool.startswith("rule:")] == ["get_sensitive_places_nearby"]
    assert "Govt. Higher Primary School" in json.dumps(steps[0].result_summary)
    # tool result was sent back to the model with the matching id
    msgs = fake.calls[1]["messages"]  # [user, assistant(tool_use), user(tool_result), ...]
    assert msgs[2]["content"][0]["tool_use_id"] == "t1" and msgs[2]["content"][0]["type"] == "tool_result"
    assert s.get(ServiceRequest, sr.id).priority == "P2"
    s.close()


def test_invalid_output_retried_then_fallback(seeded, monkeypatch):
    db = seeded
    sr = make_sr(db)
    fake = FakeLLM([final({"nonsense": True}), final({"still": "bad"})])
    monkeypatch.setattr("app.agents.runtime.loop.llm", fake)
    from app.agents.investigator import investigator

    run = get_run(run_agent(investigator, "complaint.submitted", {"id": sr.id}))
    assert len(fake.calls) == 2  # one retry with the validation errors
    assert "did not validate" in fake.calls[1]["messages"][2]["content"]
    assert run.status == "FALLBACK" and run.model == "rules" and "invalid final output" in run.error


@pytest.mark.parametrize("exc", [RuntimeError("API down"), CacheMiss("no recording"), TimeoutError("slow")])
def test_llm_errors_fall_back_to_rules(seeded, monkeypatch, exc):
    db = seeded
    sr = make_sr(db)
    monkeypatch.setattr("app.agents.runtime.loop.llm", FakeLLM([exc]))
    from app.agents.investigator import investigator

    run = get_run(run_agent(investigator, "complaint.submitted", {"id": sr.id}))
    assert run.status == "FALLBACK" and run.model == "rules" and run.output["priority"] == "P2"


def test_model_cannot_move_ward_or_invent_department(seeded, monkeypatch):
    db = seeded
    sr = make_sr(db)
    bad = {**BRIEF, "ward_id": "W13", "department_id": "NASA"}
    monkeypatch.setattr("app.agents.runtime.loop.llm", FakeLLM([final(bad)]))
    from app.agents.investigator import investigator

    run_agent(investigator, "complaint.submitted", {"id": sr.id})
    s = SessionLocal()
    got = s.get(ServiceRequest, sr.id)
    assert got.ward_id == "W12" and got.department_id == "ROADS"
    s.close()


def test_replay_cache_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(llm_mod.settings, "agent_cache_dir", str(tmp_path))
    monkeypatch.setattr(llm_mod.settings, "agent_mode", "record")
    client = llm_mod.LLMClient()
    canned = LLMResult([{"type": "text", "text": "{}"}], "end_turn", "claude-x", "live")
    monkeypatch.setattr(client, "_call", lambda *a, **k: canned)
    monkeypatch.setattr(llm_mod.settings, "anthropic_api_key", "test")
    msgs = [{"role": "user", "content": "hi"}]
    client.create(agent="a", system="s", tools=[], messages=msgs)
    monkeypatch.setattr(llm_mod.settings, "agent_mode", "replay")
    got = client.create(agent="a", system="s", tools=[], messages=msgs)
    assert got.source == "replay" and got.model == "claude-x"
    with pytest.raises(CacheMiss):
        client.create(agent="a", system="s", tools=[], messages=[{"role": "user", "content": "different"}])


def test_merge_reason_rules(seeded):
    db = seeded
    first = lodge(db, "POTHOLE", *geo.POTHOLE_SCHOOL, "Big pothole in front of the school gate, children at risk", phone="9811111111")
    second = lodge(db, "POTHOLE", geo.POTHOLE_SCHOOL[0] + 0.00003, geo.POTHOLE_SCHOOL[1], "Huge pothole near the school gate", phone="9822222222")
    from app.modules.complaints.serialize import duplicate_info

    info = duplicate_info(db, second)
    assert info["merged"] and info["parent"] == first.id and info["decided_by"] == "rules"
    assert "m away" in info["reason"] and "similar by wording" in info["reason"]


def test_model_confirms_borderline_duplicate(seeded, monkeypatch):
    """Different wording, 20 m apart: the rule alone is not sure; the model reads both and confirms -> merged."""
    db = seeded
    first = lodge(db, "POTHOLE", *geo.POTHOLE_SCHOOL, "this pothole is very big and disturbs people who are travelling")
    from app.core.bus import bus

    bus.enabled = False
    try:
        second = lodge(db, "POTHOLE", geo.POTHOLE_SCHOOL[0] + 0.00018, geo.POTHOLE_SCHOOL[1],
                       "Very big pothole. i fell in it while going. it is a busy road.", phone="9822222222")
    finally:
        bus.enabled = True
    said = {**BRIEF, "duplicate_of": first.id, "duplicate_confidence": 0.95,
            "duplicate_reason": "Both describe one large pothole on the same stretch that is hurting road users."}
    monkeypatch.setattr("app.agents.runtime.loop.llm", FakeLLM([final(said)]))
    from app.agents.investigator import investigator
    from app.modules.complaints.serialize import duplicate_info

    rid = run_agent(investigator, "complaint.submitted", {"id": second.id})
    s = SessionLocal()
    got = s.get(ServiceRequest, second.id)
    assert got.status == "MERGED" and got.parent_sr_id == first.id
    info = duplicate_info(s, got)
    assert info["decided_by"] == "model" and "Agent's reading: Both describe" in info["reason"]
    assert "rule:duplicate_confirmed_by_model" in s.scalars(select(AgentStep.tool).where(AgentStep.run_id == rid)).all()
    s.close()


def test_model_cannot_merge_far_complaint(seeded, monkeypatch):
    db = seeded
    first = lodge(db, "POTHOLE", *geo.POTHOLE_SCHOOL, "Big pothole in front of the school gate")
    from app.core.bus import bus

    bus.enabled = False
    try:
        far = lodge(db, "POTHOLE", geo.POTHOLE_SCHOOL[0] + 0.0006, geo.POTHOLE_SCHOOL[1], "Big pothole near the school", phone="9822222222")
    finally:
        bus.enabled = True
    said = {**BRIEF, "duplicate_of": first.id, "duplicate_confidence": 0.97, "duplicate_reason": "Same pothole."}
    monkeypatch.setattr("app.agents.runtime.loop.llm", FakeLLM([final(said)]))
    from app.agents.investigator import investigator

    run_agent(investigator, "complaint.submitted", {"id": far.id})
    s = SessionLocal()
    assert s.get(ServiceRequest, far.id).status == "SUBMITTED"  # ~65 m: outside the 25 m radius, never merged
    s.close()


def test_model_limit(seeded, monkeypatch):
    """LLM_AGENTS keeps the model for the named agents; the others run on rules without calling it."""
    from app.config import settings

    db = seeded
    sr = make_sr(db)
    fake = FakeLLM([final(BRIEF)])
    monkeypatch.setattr("app.agents.runtime.loop.llm", fake)
    monkeypatch.setattr(settings, "llm_agents", "auditor,ask")
    from app.agents.investigator import investigator

    run = get_run(run_agent(investigator, "complaint.submitted", {"id": sr.id}))
    assert fake.calls == [] and run.model == "rules" and "LLM_AGENTS" in run.error
    monkeypatch.setattr(settings, "llm_agents", "investigator,auditor,ask")
    run = get_run(run_agent(investigator, "complaint.submitted", {"id": sr.id}))
    assert len(fake.calls) == 1 and run.model == "claude-test"
