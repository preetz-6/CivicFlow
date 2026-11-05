"""Public agent-flow view: one case as a chain of boxes, no personal data."""
from fastapi.testclient import TestClient

from app.agents.sensing import run_sensing
from app.main import app
from app.models import HazardCluster
from app.modules.complaints.service import create_complaint
from app.seed import geo as sgeo
from tests.test_sensing import demo_feed, ingest, seeded  # noqa: F401  (fixture)


def test_citizen_case_flow(seeded):  # noqa: F811
    db = seeded
    sr = create_complaint(db, category="POTHOLE", description="Big pothole at the school gate", lat=sgeo.POTHOLE_SCHOOL[0],
                          lon=sgeo.POTHOLE_SCHOOL[1], contact_phone="9811111111")
    db.commit()
    c = TestClient(app)  # no login: public
    flow = c.get("/api/v1/public/agent-flow", params={"sr": sr.id}).json()
    assert flow["found"] and flow["sr_id"] == sr.id
    kinds = [(b["kind"], b["title"]) for b in flow["boxes"]]
    assert kinds[0] == ("person", "Citizen")
    inv = next(b for b in flow["boxes"] if b["title"] == "Case Investigator")
    assert inv["detail"]["steps"] and inv["detail"]["started_by"].startswith("Citizen lodged")
    assert inv["detail"]["how"].startswith("Rule-based")
    text = str(flow)
    assert "9811111111" not in text and "school gate" not in text  # no phone, no complaint text

    # follow live: no sr -> the latest case
    assert c.get("/api/v1/public/agent-flow").json()["sr_id"] == sr.id
    assert c.get("/api/v1/public/agent-flow", params={"sr": "SR-0000-000000"}).json()["found"] is False


def test_vehicle_case_flow_starts_with_sensing(seeded):  # noqa: F811
    db = seeded
    ingest(TestClient(app), demo_feed())
    run_sensing(force=True)
    hc = db.query(HazardCluster).filter(HazardCluster.sr_id.is_not(None)).first()
    flow = TestClient(app).get("/api/v1/public/agent-flow", params={"sr": hc.sr_id}).json()
    titles = [b["title"] for b in flow["boxes"]]
    assert titles[:3] == ["Vehicle feed", "Road Hazard Sensing", "Case Investigator"]
