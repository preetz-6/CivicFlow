"""Agent Operations feed: causes and hand-offs between agents."""
from fastapi.testclient import TestClient

from app.agents.sensing import run_sensing
from app.main import app
from app.modules.complaints.service import create_complaint
from app.seed import geo as sgeo
from tests.test_api_flow import login
from tests.test_sensing import demo_feed, ingest, seeded  # noqa: F401  (fixture)


def test_feed_shows_causes_and_handoffs(seeded):  # noqa: F811
    db = seeded
    create_complaint(db, category="POTHOLE", description="Big pothole at the school gate", lat=sgeo.POTHOLE_SCHOOL[0],
                     lon=sgeo.POTHOLE_SCHOOL[1], contact_phone="9811111111")
    db.commit()
    ingest(TestClient(app), demo_feed())
    run_sensing(force=True)

    ctl = login(TestClient(app), "control")
    items = ctl.get("/api/v1/agent-ops/feed", params={"limit": 200}).json()
    runs = [i for i in items if i["kind"] == "agent_run"]
    sensing = next(r for r in runs if r["agent"] == "sensing")
    assert sensing["cause"]["type"] == "vehicle_feed" and "detections" in sensing["cause"]["label"]
    assert any(s["kind"] == "action" and s["label"] == "Created a complaint" for s in sensing["steps"])
    # hand-off: the Case Investigator ran on a complaint that Road Hazard Sensing created
    handoff = [r for r in runs if r["agent"] == "investigator" and r["cause"]["type"] == "agent"]
    assert handoff and all(r["cause"]["run_id"] == sensing["id"] for r in handoff)
    assert "Road Hazard Sensing created" in handoff[0]["cause"]["label"]
    # the citizen's own report is a citizen-caused run, and the lodge shows as a citizen item
    assert any(r["agent"] == "investigator" and r["cause"]["type"] == "citizen" for r in runs)
    assert any(i["kind"] == "feed" for i in items) and any(i["kind"] == "citizen" for i in items)
    keys = [i["key"] for i in items]
    assert len(keys) == len(set(keys))  # stable unique keys for the UI diff

    s = ctl.get("/api/v1/agent-ops/summary").json()
    assert s["autonomous_runs"] >= len(handoff) + 1 and s["actions"] > 0
    # staff only
    assert login(TestClient(app), "officer.w12").get("/api/v1/agent-ops/feed").status_code == 403
