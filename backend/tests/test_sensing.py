"""Ingestion validation + dead-letter, and Agent 3 clustering/decisions on the demo seed."""
import io
import random
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.agents.runtime import registry
from app.agents.sensing import run_sensing
from app.config import settings
from app.core.clock import clock
from app.main import app
from app.models import (
    AgentRun, AgentStep, Crew, HazardCluster, RawDetection, RejectedDetection, ServiceRequest, Timeline,
)
from app.modules import geo
from app.modules.complaints.service import create_complaint
from app.seed import build
from app.seed import geo as sgeo

KEY = {"X-API-Key": settings.oem_sim_api_key}


@pytest.fixture
def seeded(db):
    build.rng.seed(2026)
    build.Seeder(db).run()
    db.commit()
    registry.register_agents()
    return db


def rec(i, lat, lon, vehicle, conf=0.86, hours_ago=5, **kw):
    return {"source_record_id": f"t-{i:06d}", "lat": lat, "lon": lon, "hazard_type": "POTHOLE",
            "detected_at": (clock.now() - timedelta(hours=hours_ago)).isoformat(), "confidence": conf,
            "speed_kmph": 30, "vertical_accel_peak_g": 1.8, "vehicle_ref": vehicle, **kw}


def jit(lat, lon, rng, m=6):
    d = m / 111_000
    return lat + rng.uniform(-d, d), lon + rng.uniform(-d, d)


def demo_feed() -> list[dict]:
    """Same shape the simulator sends: true potholes, speed breakers, noise."""
    rng = random.Random(7)
    out, i = [], 0
    for pid, kind, (lat, lon), n in sgeo.TRUE_POTHOLES:
        conf = 0.6 if kind == "weak" else 0.86
        for v in range(n):
            for _ in range(2):
                i += 1
                out.append(rec(i, *jit(lat, lon, rng), f"veh-{pid}-{v}", conf=conf, hours_ago=rng.uniform(1, 60)))
    for name, (lat, lon) in sgeo.SPEED_BREAKERS:
        for v in range(6):
            i += 1
            out.append(rec(i, *jit(lat, lon, rng, 3), f"veh-sb-{name[:10]}-{v}", conf=0.9))
    for _ in range(25):  # one-off noise far from everything
        i += 1
        out.append(rec(i, rng.uniform(12.882, 12.948), rng.uniform(77.462, 77.548), f"noise-{i}", conf=0.4))
    return out


def ingest(client, records, **headers):
    r = client.post("/api/v1/ingest/detections", json=records, headers={**KEY, **headers})
    assert r.status_code == 200, r.text
    return r.json()


# ------------------------------------------------------------------------------ ingestion
def test_validation_and_dead_letter(seeded):
    c = TestClient(app)
    lat, lon = sgeo.POTHOLE_ARTERIAL
    batch = [
        rec(1, lat, lon, "v1"),
        rec(2, 13.20, 77.60, "v1"),  # outside city
        rec(3, lat, lon, "v1", hours_ago=-3),  # future
        rec(4, lat, lon, "v1", hours_ago=24 * 31),  # too old
        rec(5, lat, lon, "v1", conf=1.7),  # bad confidence
        {**rec(6, lat, lon, "v1"), "hazard_type": "ALIEN"},
        {**rec(7, lat, lon, "v1"), "vin": "MA1XYZ", "rider_name": "Ravi"},  # personal data
        {**rec(8, lat, lon, "v1"), "confidence": None},  # defaults to 0.5
        rec(1, lat, lon, "v1"),  # duplicate within batch
        {**rec(9, lat, lon, "v1"), "hazard_type": "rough surface"},
    ]
    res = ingest(c, batch)
    assert res["accepted"] == 3 and res["rejected"] == 7 and res["duplicates"] == 1
    reasons = {r["reason"] for r in res["rejections"]}
    assert {"outside city boundary", "detected_at is in the future", "detected_at older than 30 days",
            "confidence 1.7 out of range", "unknown hazard_type 'ALIEN'",
            "personal data not accepted: rider_name, vin"} <= reasons
    db = seeded
    assert db.scalar(select(RawDetection).where(RawDetection.source_record_id == "t-000008")).confidence == 0.5
    assert db.scalar(select(RawDetection).where(RawDetection.source_record_id == "t-000009")).hazard_type == "ROUGH_SURFACE"
    dead = db.scalars(select(RejectedDetection)).all()
    assert len(dead) == 7  # never silently dropped
    pii = next(d for d in dead if d.source_record_id == "t-000007")
    assert "vin" not in pii.raw_payload and "rider_name" not in pii.raw_payload  # not even in the dead letter
    assert ingest(c, [rec(1, lat, lon, "v1")])["duplicates"] == 1  # across batches too


def test_auth_idempotency_limits_and_csv(seeded):
    c = TestClient(app)
    lat, lon = sgeo.POTHOLE_ARTERIAL
    assert c.post("/api/v1/ingest/detections", json=[rec(1, lat, lon, "v")]).status_code == 401
    assert c.post("/api/v1/ingest/detections", json=[rec(1, lat, lon, "v")], headers={"X-API-Key": "nope"}).status_code == 401
    first = ingest(c, [rec(1, lat, lon, "v")], **{"Idempotency-Key": "batch-1"})
    again = ingest(c, [rec(1, lat, lon, "v")], **{"Idempotency-Key": "batch-1"})
    assert first["accepted"] == 1 and again["idempotent_replay"] is True and again["accepted"] == 1
    big = [rec(i, lat, lon, "v") for i in range(1001)]
    assert c.post("/api/v1/ingest/detections", json=big, headers=KEY).status_code == 413
    csv = "source_record_id,lat,lon,hazard_type,detected_at,confidence,vehicle_ref\n" + "\n".join(
        f"csv-{i},{lat},{lon},POTHOLE,{(clock.now() - timedelta(hours=2)).isoformat()},0.9,veh{i}" for i in range(3))
    r = c.post("/api/v1/ingest/detections/csv", files={"file": ("d.csv", io.BytesIO(csv.encode()), "text/csv")}, headers=KEY)
    assert r.json()["accepted"] == 3


# ------------------------------------------------------------------------------ sensing
def test_sensing_end_to_end_on_demo_seed(seeded):
    db = seeded
    # the live demo's citizen complaint at the school
    school = create_complaint(db, category="POTHOLE", description="Big pothole at the school gate",
                              lat=sgeo.POTHOLE_SCHOOL[0], lon=sgeo.POTHOLE_SCHOOL[1], contact_phone="9811111111")
    db.commit()
    ingest(TestClient(app), demo_feed())
    rid = run_sensing(force=True)
    while run_sensing() is not None:  # each run handles at most 10 clusters; leftovers go next tick
        pass
    db.expire_all()
    run = db.get(AgentRun, rid)
    assert run.status == "FALLBACK" and run.model == "rules"

    def cluster_near(lat, lon) -> HazardCluster:
        return db.scalar(select(HazardCluster).where(geo.within(HazardCluster.center, lat, lon, 15)))

    # speed breakers are filtered and visible as such
    for name, (lat, lon) in sgeo.SPEED_BREAKERS:
        h = cluster_near(lat, lon)
        assert h.status == "FILTERED" and "speed breaker" in h.filter_reason
    # corroborates the citizen complaint
    h = cluster_near(*sgeo.POTHOLE_SCHOOL)
    assert h.status == "CORROBORATED" and h.sr_id == school.id
    sr = db.get(ServiceRequest, school.id)
    assert sr.corroboration_count == 7
    assert any("Confirmed by 7 connected vehicles" in t.remarks for t in db.scalars(select(Timeline).where(Timeline.sr_id == sr.id)))
    # creates a complaint on the arterial road that no one reported -> then the Case Investigator runs on it
    h = cluster_near(*sgeo.POTHOLE_ARTERIAL)
    assert h.status == "CREATED"
    new = db.get(ServiceRequest, h.sr_id)
    assert new.source == "VEHICLE_FEED" and "Mysore Road" in new.description and new.corroboration_count == 9
    assert db.scalar(select(AgentRun).where(AgentRun.agent == "investigator", AgentRun.subject_id == new.id))
    assert new.priority == "P2"  # arterial road
    # repair failure at the spot repaired 10 days ago
    h = cluster_near(*sgeo.POTHOLE_REPAIRED)
    assert h.status == "REPAIR_FAILURE" and h.flagged_wo_id
    assert db.get(Crew, "W15-A").audit_priority == "HIGH"
    # weak clusters go to review, a single-vehicle cluster is filtered
    weak = {pid: cluster_near(lat, lon) for pid, kind, (lat, lon), n in sgeo.TRUE_POTHOLES if kind == "weak"}
    assert weak["PH-13"].status == "REVIEW" and weak["PH-14"].status == "REVIEW"
    assert weak["PH-15"].status == "FILTERED" and "Single vehicle" in weak["PH-15"].filter_reason
    # seeded open complaints next to true potholes are corroborated, not duplicated
    for pid, kind, (lat, lon), n in sgeo.TRUE_POTHOLES:
        if kind == "seeded_open":
            assert cluster_near(lat, lon).status == "CORROBORATED", pid
    # actions are visible in the Activity Log
    tools = set(db.scalars(select(AgentStep.tool).where(AgentStep.run_id == rid)))
    assert {"action:create_system_complaint", "action:attach_corroboration", "action:flag_repair_failure"} <= tools
    # second run with no new data does nothing
    assert run_sensing() is None


def test_sensing_does_not_create_for_weak_cluster_even_if_model_says_so(seeded, monkeypatch):
    import json

    from app.adapters.llm import LLMResult

    db = seeded
    lat, lon = 12.9420, 77.5100  # PH-13 (weak)
    ingest(TestClient(app), [rec(i, lat, lon, f"v{i % 2}", conf=0.6) for i in range(4)])
    from app.agents.sensing import recluster

    class Fake:
        def available(self):
            return True

        def create(self, **kw):
            ids = [c["cluster_id"] for c in json.loads(kw["messages"][0]["content"].split("Input:\n", 1)[1])["candidates"]]
            return LLMResult([{"type": "text", "text": json.dumps({"summary": "x", "confidence": 0.9, "decisions": [
                {"cluster_id": i, "decision": "CREATE", "reason": "looks bad"} for i in ids]})}], "end_turn", "claude-test", "live")

    monkeypatch.setattr("app.agents.runtime.loop.llm", Fake())
    run_sensing(force=True)
    db.expire_all()
    h = db.scalar(select(HazardCluster))
    assert h.status == "REVIEW" and h.sr_id is None
