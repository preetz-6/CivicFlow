"""API-level happy path + scoping (mirrors the Playwright test, minus the agents)."""
import io
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.core.clock import clock
from app.main import app
from app.modules.complaints import handlers
from app.modules.media.service import read_exif, write_exif
from tests.factories import TEST_PASSWORD, W12_PT


def jpeg(lat=None, lon=None, t=None, color=(90, 90, 90)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (64, 48), color).save(buf, format="JPEG")
    return write_exif(buf.getvalue(), lat, lon, t)


def login(c: TestClient, username: str) -> TestClient:
    """Tests on the small factory world use TEST_PASSWORD; tests on the real seed use the seeded role passwords."""
    from app.seed.build import PASSWORDS

    role = {"citizen": "CITIZEN", "officer": "WARD_OFFICER", "zonal": "WARD_OFFICER", "field": "FIELD_TEAM",
            "control": "CONTROL_ROOM"}[username.split(".")[0].rstrip("0123456789")]
    for pw in (TEST_PASSWORD, PASSWORDS[role]):
        r = c.post("/api/v1/auth/login", json={"username": username, "password": pw})
        if r.status_code == 200:
            assert "cf_session" in c.cookies
            return c
    raise AssertionError(f"could not log in as {username}: {r.text}")


@pytest.fixture
def client(world):
    handlers.register()
    return lambda: TestClient(app)


def lodge(c, **kw):
    data = {"category": "POTHOLE", "description": "Big pothole near the school gate, kids at risk",
            "lat": W12_PT[0], "lon": W12_PT[1], "contact_phone": "9000000099", "language": "kn", **kw}
    files = {"photo": ("p.jpg", jpeg(*W12_PT, clock.now()), "image/jpeg")}
    r = c.post("/api/v1/complaints", data=data, files=files)
    assert r.status_code == 201, r.text
    return r.json()


def test_exif_roundtrip():
    t = clock.now()
    meta = read_exif(jpeg(12.9101, 77.4854, t))
    assert abs(meta["lat"] - 12.9101) < 1e-5 and abs(meta["lon"] - 77.4854) < 1e-5
    assert meta["time"] == t.replace(microsecond=0)
    assert read_exif(jpeg())["lat"] is None


def test_unknown_user_cannot_login(client):
    assert client().post("/api/v1/auth/login", json={"username": "newbie", "password": "x"}).status_code == 401


def test_wrong_password_rejected_and_right_one_sets_cookie(client):
    c = client()
    assert c.post("/api/v1/auth/login", json={"username": "officer.w12", "password": "wrong"}).status_code == 401
    assert "cf_session" not in c.cookies
    r = c.post("/api/v1/auth/login", json={"username": "officer.w12", "password": TEST_PASSWORD})
    assert r.status_code == 200 and r.json()["role"] == "WARD_OFFICER" and "cf_session" in c.cookies
    assert "password_hash" not in r.json()
    assert c.get("/api/v1/auth/me").json()["username"] == "officer.w12"


def test_citizens_cannot_log_in(client):
    r = client().post("/api/v1/auth/login", json={"username": "citizen1", "password": TEST_PASSWORD})
    assert r.status_code == 401 and "do not need to log in" in r.json()["detail"]


def test_full_happy_path(client):
    citizen = client()
    ack = lodge(citizen)
    assert ack["ward_id"] == "W12" and ack["status"] == "SUBMITTED"
    no, code = ack["grievance_no"], ack["tracking_code"]
    tv = citizen.get("/api/v1/complaints/track", params={"no": no, "code": code}).json()
    assert tv["status"] == "SUBMITTED" and len(tv["citizen_photos"]) == 1
    assert citizen.get("/api/v1/complaints/track", params={"no": no, "code": "WRONG"}).status_code == 404

    officer = login(client(), "officer.w12")
    q = officer.get("/api/v1/officer/queue").json()
    assert any(i["id"] == no for i in q["items"])
    assert officer.post(f"/api/v1/complaints/{no}/accept", json={}).json()["status"] == "ASSIGNED"
    r = officer.post(f"/api/v1/complaints/{no}/work-orders", data={"crew_id": "W12-A", "scope": "Fill pothole"},
                     files={"before_photo": ("b.jpg", jpeg(*W12_PT, clock.now()), "image/jpeg")})
    assert r.status_code == 201, r.text
    wo = r.json()["id"]

    field = login(client(), "field.w12a")
    jobs = field.get("/api/v1/field/jobs").json()
    assert [j["id"] for j in jobs] == [wo]
    assert "contact_phone" not in jobs[0]
    detail = field.get(f"/api/v1/complaints/{no}").json()
    assert detail["contact_phone"] is None and detail["contact_name"] is None
    assert field.post(f"/api/v1/field/jobs/{wo}/complete").status_code == 409  # not started
    field.post(f"/api/v1/field/jobs/{wo}/start")
    assert field.post(f"/api/v1/field/jobs/{wo}/complete").status_code == 422  # no after photo
    clock.advance(timedelta(hours=2))
    up = field.post(f"/api/v1/field/jobs/{wo}/photos", data={"kind": "AFTER"},
                    files={"photo": ("a.jpg", jpeg(*W12_PT, clock.now(), (40, 40, 40)), "image/jpeg")})
    assert up.status_code == 200 and up.json()["exif_lat"]
    assert field.post(f"/api/v1/field/jobs/{wo}/complete").json()["status"] == "COMPLETED"
    assert field.post(f"/api/v1/work-orders/{wo}/approve").status_code == 403  # cannot verify own work

    control = login(client(), "control")
    assert [v["id"] for v in control.get("/api/v1/control/verification").json()] == [wo]
    r = control.post(f"/api/v1/work-orders/{wo}/approve").json()
    assert r["status"] == "VERIFIED"
    tv = citizen.get("/api/v1/complaints/track", params={"no": no, "code": code}).json()
    assert tv["status"] == "RESOLVED", tv["timeline"]  # handler VERIFIED -> RESOLVED ran
    assert tv["before_photos"] and tv["after_photos"] and tv["can_confirm"]
    img = citizen.get(tv["after_photos"][0]["url"])
    assert img.status_code == 200 and img.headers["content-type"] == "image/jpeg"

    r = citizen.post(f"/api/v1/complaints/{no}/confirm", json={"code": code, "rating": 5})
    assert r.json()["status"] == "CLOSED"
    tv = citizen.get("/api/v1/complaints/track", params={"no": no, "code": code}).json()
    assert tv["feedback_rating"] == 5
    assert [t["stage"] for t in tv["timeline"]][-1] == "Closed"
    stats = citizen.get("/api/v1/public/stats").json()
    assert stats["resolved_citizen_confirmed"] == 1 and stats["resolved_auto_closed"] == 0


def test_officer_scoped_to_ward(client):
    ack = lodge(client())
    other = login(client(), "officer.w7")
    assert all(i["id"] != ack["grievance_no"] for i in other.get("/api/v1/officer/queue").json()["items"])
    assert other.get(f"/api/v1/complaints/{ack['grievance_no']}").status_code == 403
    assert other.post(f"/api/v1/complaints/{ack['grievance_no']}/accept", json={}).status_code == 403


def test_field_team_cannot_see_other_crew_jobs(client):
    ack = lodge(client())
    officer = login(client(), "officer.w12")
    officer.post(f"/api/v1/complaints/{ack['grievance_no']}/accept", json={})
    wo = officer.post(f"/api/v1/complaints/{ack['grievance_no']}/work-orders",
                      data={"crew_id": "W12-A", "scope": "x"}).json()["id"]
    other = login(client(), "field.w7a")
    assert other.get("/api/v1/field/jobs").json() == []
    assert other.get(f"/api/v1/field/jobs/{wo}").status_code == 403


def test_emergency_keyword_sets_p1(client):
    ack = lodge(client(), description="Open manhole on the footpath, a child fell in yesterday")
    officer = login(client(), "officer.w12")
    d = officer.get(f"/api/v1/complaints/{ack['grievance_no']}").json()
    assert d["priority"] == "P1" and d["emergency"] is True


def test_outside_city_rejected(client):
    r = client().post("/api/v1/complaints", data={"category": "POTHOLE", "description": "Pothole in Mysuru city",
                                                  "lat": 12.30, "lon": 76.64, "contact_phone": "9000000000"})
    assert r.status_code == 400
