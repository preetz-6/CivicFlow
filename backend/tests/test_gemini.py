"""Gemini provider: message translation + a full agent run against a scripted fake Gemini client."""
import base64
import json

import pytest
from google.genai import types
from sqlalchemy import select

from app.adapters import gemini
from app.adapters import llm as llm_mod
from app.agents.runtime import registry
from app.agents.runtime.loop import run_agent
from app.core.db import SessionLocal
from app.models import AgentRun, AgentStep, ServiceRequest
from app.seed import build, geo

SIG = b"\x01\x02signature\xff"


def resp(parts, finish="STOP"):
    return types.GenerateContentResponse(candidates=[types.Candidate(
        content=types.Content(role="model", parts=parts), finish_reason=finish)], model_version="gemini-test")


def test_translation_roundtrip_keeps_thought_signature():
    r = resp([types.Part(function_call=types.FunctionCall(id="c1", name="get_road_class", args={"lat": 1, "lon": 2}),
                         thought_signature=SIG)])
    blocks, stop = gemini.to_blocks(r)
    assert stop == "tool_use" and blocks[0]["name"] == "get_road_class" and blocks[0]["input"] == {"lat": 1, "lon": 2}
    json.dumps(blocks)  # must be cacheable (record/replay)
    msgs = [{"role": "user", "content": "hi"},
            {"role": "assistant", "content": blocks},
            {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "c1", "content": '{"road_class": "ARTERIAL"}'}]},
            {"role": "user", "content": [{"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                                                     "data": base64.b64encode(b"jpg").decode()}},
                                         {"type": "text", "text": "look"}]}]
    c = gemini.to_contents(msgs)
    assert [x.role for x in c] == ["user", "model", "user", "user"]
    assert c[1].parts[0].thought_signature == SIG  # sent back unchanged
    fr = c[2].parts[0].function_response
    assert fr.name == "get_road_class" and fr.id == "c1" and fr.response == {"result": {"road_class": "ARTERIAL"}}
    assert c[3].parts[0].inline_data.data == b"jpg"


def test_finish_reasons_map():
    assert gemini.to_blocks(resp([types.Part(text="x")], "SAFETY"))[1] == "refusal"
    assert gemini.to_blocks(resp([types.Part(text="x")], "MAX_TOKENS"))[1] == "max_tokens"
    assert gemini.to_blocks(resp([types.Part(text="{}")]))[1] == "end_turn"


class FakeModels:
    def __init__(self, script):
        self.script, self.calls = list(script), []

    def generate_content(self, *, model, contents, config):
        self.calls.append({"model": model, "contents": contents, "config": config})
        return self.script.pop(0)


class FakeClient:
    def __init__(self, script):
        self.models = FakeModels(script)


@pytest.fixture
def seeded(db):
    build.rng.seed(2026)
    build.Seeder(db).run()
    db.commit()
    registry.register_agents()
    return db


def test_investigator_runs_on_gemini(seeded, monkeypatch):
    from app.core.bus import bus
    from app.modules.complaints.service import create_complaint

    db = seeded
    bus.enabled = False
    try:
        sr = create_complaint(db, category="POTHOLE", description="Pothole at the school gate", lat=geo.POTHOLE_SCHOOL[0],
                              lon=geo.POTHOLE_SCHOOL[1], contact_phone="9811111111")
        db.commit()
    finally:
        bus.enabled = True
    brief = {"category": "POTHOLE", "priority": "P2", "department_id": "ROADS", "ward_id": "W12",
             "rationale": ["School 40 m away (Gemini)"], "confidence": 0.83}
    fake = FakeClient([
        resp([types.Part(function_call=types.FunctionCall(id="g1", name="get_sensitive_places_nearby",
                                                          args={"lat": geo.POTHOLE_SCHOOL[0], "lon": geo.POTHOLE_SCHOOL[1]}),
                         thought_signature=SIG)]),
        resp([types.Part(text=json.dumps(brief))]),
    ])
    monkeypatch.setattr(gemini, "client", lambda key: fake)
    monkeypatch.setattr(llm_mod.settings, "llm_provider", "gemini")
    monkeypatch.setattr(llm_mod.settings, "gemini_api_key", "test-key")
    monkeypatch.setattr(llm_mod.settings, "agent_mode", "live")
    from app.agents.investigator import investigator

    rid = run_agent(investigator, "complaint.submitted", {"id": sr.id})
    s = SessionLocal()
    run = s.get(AgentRun, rid)
    assert run.status == "OK" and run.model == "gemini-test" and run.confidence == 0.83
    assert [st.tool for st in s.scalars(select(AgentStep).where(AgentStep.run_id == rid)) if not st.tool.startswith("rule:")] == ["get_sensitive_places_nearby"]
    assert s.get(ServiceRequest, sr.id).priority == "P2"
    s.close()
    second = fake.models.calls[1]
    cfg = second["config"]
    assert cfg.automatic_function_calling.disable is True and cfg.tools[0].function_declarations
    fr = second["contents"][-1].parts[0].function_response
    assert fr.name == "get_sensitive_places_nearby" and "Govt. Higher Primary School" in json.dumps(fr.response)
    assert second["contents"][1].parts[0].thought_signature == SIG
