"""Replay must hit when the demo story repeats (different clock / numbering), and replayed answers must never act
on the wrong record."""
import json

import pytest
from sqlalchemy import select

from app.adapters.llm import LLMResult, cache_key
from app.agents.runtime import registry
from app.agents.runtime.loop import run_agent
from app.core.db import SessionLocal
from app.models import AgentRun, ServiceRequest
from app.seed import build, geo

T = [{"name": "get_ward_for_location"}]


def msg(no, ts, lat, desc):
    return [{"role": "user", "content": json.dumps({"grievance_no": no, "filed_at": ts, "lat": lat, "description": desc})}]


def test_key_ignores_clock_numbering_and_gps_noise():
    a = cache_key("investigator", "m", "sys", T, msg("SR-2026-001273", "2026-11-05T10:17:00+05:30", 12.909912, "Big pothole"))
    b = cache_key("investigator", "m", "sys", T, msg("SR-2026-001290", "2026-11-07T18:02:11.5+05:30", 12.909903, "big  pothole"))
    assert a == b


def test_key_changes_with_story_turn_prompt_and_agent():
    base = msg("SR-2026-001273", "2026-11-05T10:17:00+05:30", 12.9099, "Big pothole")
    k = cache_key("investigator", "m", "sys", T, base)
    assert k != cache_key("investigator", "m", "sys", T, msg("SR-2026-001273", "2026-11-05T10:17:00+05:30", 12.9099, "Garbage"))
    assert k != cache_key("investigator", "m", "sys", T, base + [{"role": "assistant", "content": []}])
    assert k != cache_key("investigator", "m", "other prompt", T, base)
    assert k != cache_key("auditor", "m", "sys", T, base)


@pytest.fixture
def seeded(db):
    build.rng.seed(2026)
    build.Seeder(db).run()
    db.commit()
    registry.register_agents()
    return db


class Fake:
    mode = "replay"

    def __init__(self, out):
        self.out = out

    def available(self):
        return True

    def create(self, **kw):
        return LLMResult([{"type": "text", "text": json.dumps(self.out)}], "end_turn", "replay-model", "replay")


def test_replayed_duplicate_of_a_far_record_is_not_merged(seeded, monkeypatch):
    from app.agents.investigator import investigator
    from app.core.bus import bus
    from app.modules.complaints.service import create_complaint

    db = seeded
    bus.enabled = False
    try:
        far = create_complaint(db, category="POTHOLE", description="Pothole on Ideal Homes Road", lat=12.9210, lon=77.5300,
                               contact_phone="9811111110")
        sr = create_complaint(db, category="POTHOLE", description="Pothole at the school gate", lat=geo.POTHOLE_SCHOOL[0],
                              lon=geo.POTHOLE_SCHOOL[1], contact_phone="9811111111")
        db.commit()
    finally:
        bus.enabled = True
    bad = {"category": "POTHOLE", "priority": "P2", "department_id": "ROADS", "ward_id": "W12", "duplicate_of": far.id,
           "duplicate_confidence": 0.97, "rationale": ["recorded answer"], "confidence": 0.9}
    monkeypatch.setattr("app.agents.runtime.loop.llm", Fake(bad))
    rid = run_agent(investigator, "complaint.submitted", {"id": sr.id})
    s = SessionLocal()
    assert s.get(ServiceRequest, sr.id).status == "SUBMITTED"  # not merged into a complaint 5 km away
    assert s.get(AgentRun, rid).output["duplicate_of"] != far.id
    s.close()


def test_rain_complaints_use_rules_in_record_and_replay(seeded):
    from app.agents.investigator import investigator

    assert investigator.use_llm({"source": "CITIZEN_WEB", "category_chosen": "POTHOLE"}, "replay") is True
    assert investigator.use_llm({"source": "CITIZEN_WEB", "category_chosen": "WATERLOGGING"}, "record") is False
    assert investigator.use_llm({"source": "VEHICLE_FEED", "category_chosen": "POTHOLE"}, "replay") is False
    assert investigator.use_llm({"source": "CITIZEN_WEB", "category_chosen": "WATERLOGGING"}, "live") is True


def test_cautious_model_still_merges_when_rule_is_sure_and_p1_is_capped(seeded, monkeypatch):
    """Gemini said duplicate 0.65 and P1 for 'two wheelers falling': the radius rule merges, P1 is capped to P2."""
    from app.agents.investigator import investigator
    from app.core.bus import bus
    from app.modules.complaints.service import create_complaint

    db = seeded
    bus.enabled = False
    try:
        first = create_complaint(db, category="POTHOLE", description="Huge pothole near the school gate, kids at risk",
                                 lat=geo.POTHOLE_SCHOOL[0], lon=geo.POTHOLE_SCHOOL[1], contact_phone="9811111111")
        sr = create_complaint(db, category="POTHOLE", description="Pothole at the school gate, two wheelers falling",
                              lat=geo.POTHOLE_SCHOOL[0] - 0.00002, lon=geo.POTHOLE_SCHOOL[1], contact_phone="9811111112")
        db.commit()
    finally:
        bus.enabled = True
    cautious = {"category": "POTHOLE", "priority": "P1", "department_id": "ROADS", "ward_id": "W12", "duplicate_of": first.id,
                "duplicate_confidence": 0.65, "rationale": ["recorded answer"], "confidence": 0.8}
    monkeypatch.setattr("app.agents.runtime.loop.llm", Fake(cautious))
    rid = run_agent(investigator, "complaint.submitted", {"id": sr.id})
    s = SessionLocal()
    got = s.get(ServiceRequest, sr.id)
    assert got.status == "MERGED" and got.parent_sr_id == first.id
    assert s.get(AgentRun, rid).output["duplicate_confidence"] >= 0.9 and s.get(AgentRun, rid).output["priority"] == "P2"
    s.close()
