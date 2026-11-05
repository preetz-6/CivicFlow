"""Agent 5 Surge Commander: rain scenario -> 2 incidents, advisory, publish -> ticker, summary."""
import random
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.agents.runtime import registry
from app.agents.surge import run_surge_check
from app.core.clock import clock
from app.main import app
from app.models import AgentRun, Incident, Notification, ServiceRequest, WeatherAlert
from app.modules.complaints.service import create_complaint
from app.seed import build, geo
from tests.test_api_flow import login

TEXTS = {
    "WATERLOGGING": ["Knee-deep water, vehicles stuck", "Road flooded after the rain", "Water entering shops",
                     "Bikes cannot pass, water everywhere", "Underpass full of water", "Flooding near my house"],
    "DRAIN_BLOCKED": ["Drain overflowing onto the road", "Storm drain choked, water backing up", "Sewage mixing with rain water"],
}


@pytest.fixture
def seeded(db):
    build.rng.seed(2026)
    build.Seeder(db).run()
    db.commit()
    registry.register_agents()
    return db


def burst(db, center, n, cat, seed):
    rng = random.Random(seed)
    ids = []
    for k in range(n):
        d = 400 / 111_000
        sr = create_complaint(db, category=cat, description=f"{rng.choice(TEXTS[cat])} (report {seed}-{k})",
                              lat=center[0] + rng.uniform(-d, d), lon=center[1] + rng.uniform(-d, d),
                              contact_phone=f"97{seed:02d}{k:06d}")
        db.commit()
        ids.append(sr.id)
        clock.advance(timedelta(minutes=1))
    return ids


def test_rain_scenario(seeded):
    db = seeded
    db.add(WeatherAlert(title="Heavy rain warning (SIMULATED)", severity="ORANGE", active=True, issued_at=clock.now(),
                        expires_at=clock.now() + timedelta(hours=6)))
    db.commit()
    a = burst(db, geo.KENGERI_UNDERPASS, 17, "WATERLOGGING", 1)
    b = burst(db, geo.RR_NAGAR_ARCH_DRAIN, 8, "DRAIN_BLOCKED", 2)
    rid = run_surge_check()
    db.expire_all()
    run = db.get(AgentRun, rid)
    assert run.status == "FALLBACK" and run.output["mode"] == "NEW_INCIDENTS"
    incs = {i.name: i for i in db.scalars(select(Incident))}
    assert set(incs) == {"Kengeri Underpass Waterlogging", "RR Nagar Arch Drain Overflow"}
    k, r = incs["Kengeri Underpass Waterlogging"], incs["RR Nagar Arch Drain Overflow"]
    open_a = [s for s in (db.get(ServiceRequest, i) for i in a) if s.status != "MERGED"]
    assert k.report_count == len(open_a) and all(s.incident_id == k.id for s in open_a)
    assert k.severity in ("SEVERE", "HIGH") and r.severity in ("HIGH", "MEDIUM")
    assert "jetting machine" in k.crew_suggestion
    assert "Kengeri Underpass" in k.advisory_draft and "crews deployed" in k.advisory_draft
    assert "Heavy rain warning" in k.summary
    assert db.scalar(select(Notification).where(Notification.event == "INCIDENT", Notification.related_sr_id == a[0]))

    # a late report near the underpass joins the incident automatically
    late = burst(db, geo.KENGERI_UNDERPASS, 1, "WATERLOGGING", 3)[0]
    run_surge_check()
    db.expire_all()
    late_sr = db.get(ServiceRequest, late)
    if late_sr.status == "MERGED":  # the Case Investigator may link it to a duplicate that is already in the incident
        late_sr = db.get(ServiceRequest, late_sr.parent_sr_id)
    assert late_sr.incident_id == k.id

    # Control Room publishes -> public ticker
    ctl = login(TestClient(app), "control")
    assert login(TestClient(app), "officer.w12").post(f"/api/v1/incidents/{k.id}/publish", json={}).status_code == 403
    assert ctl.post(f"/api/v1/incidents/{k.id}/publish", json={}).json()["advisory_published"] is True
    ticker = TestClient(app).get("/api/v1/public/ticker").json()
    assert ticker[0]["id"] == f"incident-{k.id}" and "Kengeri Underpass" in ticker[0]["text"] and ticker[0]["new"]
    listing = ctl.get("/api/v1/incidents").json()
    assert any(x["display_name"].startswith("Kengeri Underpass Waterlogging — ") for x in listing)

    # situation summary refreshed every simulated hour
    clock.advance(timedelta(hours=1, minutes=1))
    rid2 = run_surge_check()
    db.expire_all()
    assert db.get(AgentRun, rid2).output["mode"] == "SUMMARY"


def test_no_surge_without_volume_or_alert(seeded):
    db = seeded
    burst(db, geo.KENGERI_UNDERPASS, 6, "WATERLOGGING", 4)
    assert run_surge_check() is None  # 6 reports and no weather alert: not a surge
    assert db.scalar(select(Incident)) is None
