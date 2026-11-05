"""Live map pins: open cases with photo, status and the agent's decision."""
from fastapi.testclient import TestClient

from app.main import app
from app.modules.complaints.service import create_complaint
from app.seed import geo as sgeo
from tests.test_api_flow import login
from tests.test_sensing import seeded  # noqa: F401  (fixture)


def test_map_pins(seeded):  # noqa: F811
    db = seeded
    sr = create_complaint(db, category="POTHOLE", description="Pothole near the gate", lat=sgeo.POTHOLE_SCHOOL[0],
                          lon=sgeo.POTHOLE_SCHOOL[1], contact_phone="9811111111")
    db.commit()
    ctl = login(TestClient(app), "control")
    pins = ctl.get("/api/v1/officer/map").json()
    pin = next(p for p in pins if p["id"] == sr.id)
    assert pin["lat"] and pin["lon"] and pin["sla"]["label"] and pin["fixed"] is False
    assert "photo_url" in pin and "description" not in pin
    assert pin["analysis_decision"]  # the Case Investigator ran on submit
    assert TestClient(app).get("/api/v1/officer/map").status_code == 401
