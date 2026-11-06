"""Ask CivicFlow: questions answered from live data (rule-based version in tests, no model)."""
from fastapi.testclient import TestClient

from app.agents.sensing import run_sensing
from app.main import app
from app.modules.complaints.service import create_complaint
from app.seed import geo as sgeo
from tests.test_api_flow import login
from tests.test_sensing import demo_feed, ingest, seeded  # noqa: F401  (fixture)


def ask(c, q):
    r = c.post("/api/v1/ask", json={"question": q})
    assert r.status_code == 200, r.text
    return r.json()


def test_ask_questions(seeded):  # noqa: F811
    db = seeded
    sr = create_complaint(db, category="POTHOLE", description="Pothole at the school gate", lat=sgeo.POTHOLE_SCHOOL[0],
                          lon=sgeo.POTHOLE_SCHOOL[1], contact_phone="9811111111")
    db.commit()
    ingest(TestClient(app), demo_feed())
    run_sensing(force=True)
    ctl = login(TestClient(app), "control")

    a = ask(ctl, "Which ward is worst this week and why?")
    assert "W1" in a["answer"] and a["points"] and any(s["label"] == "ward summary" for s in a["steps"])

    a = ask(ctl, f"Why is {sr.id} late?")
    assert sr.id in a["answer"] and a["cases"] == [sr.id] and "not been accepted" in a["answer"]

    a = ask(ctl, "How many potholes did vehicles find that no citizen reported?")
    assert "vehicle feed found" in a["answer"] and a["cases"]

    a = ask(ctl, "What does the citizen charter say about reopening?")
    assert a["sources"] and "reopen" in a["answer"].lower()

    a = ask(ctl, "Which crews are overloaded?")
    assert "overloaded" in a["answer"]

    hist = ctl.get("/api/v1/ask/history").json()
    assert len(hist) == 5 and hist[0]["question"].startswith("Which crews")
    # the Agent Operations feed shows who asked; the public views never show these runs
    feed = ctl.get("/api/v1/agent-ops/feed", params={"limit": 300}).json()
    assert any(i.get("agent") == "ask" and "asked:" in i["cause"]["label"] for i in feed)
    pub = TestClient(app).get("/api/v1/public/agent-activity", params={"limit": 20}).json()
    assert all(x["agent"] != "ask" for x in pub["latest"])
    # staff only
    assert TestClient(app).post("/api/v1/ask", json={"question": "hello there"}).status_code == 401
    assert login(TestClient(app), "field.w12a").post("/api/v1/ask", json={"question": "hello there"}).status_code == 403


def test_ask_model_path(seeded, monkeypatch):  # noqa: F811
    """The model chooses the lookups and writes the answer (scripted fake model)."""
    from tests.test_investigator import FakeLLM, final, tool_use

    fake = FakeLLM([tool_use("ward_summary", {"days": 7}),
                    final({"answer": "W12 has the most open cases.", "points": ["W12: 3 open"], "cases": [],
                           "sources": [], "confidence": 0.8})])
    monkeypatch.setattr("app.agents.runtime.loop.llm", fake)
    a = ask(login(TestClient(app), "control"), "Which ward has the most open cases?")
    assert a["answer"] == "W12 has the most open cases." and a["how"].startswith("AI model")
    assert [s["label"] for s in a["steps"]] == ["ward summary"]
    assert "ward_summary" in [t["name"] for t in fake.calls[0]["tools"]]
