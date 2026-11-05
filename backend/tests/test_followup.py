"""Agent 2 Follow-up & Escalation on the demo seed."""
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.agents.followup import run_followup_timer
from app.agents.runtime import registry
from app.core.clock import clock
from app.main import app
from app.models import (
    AgentRun, Escalation, MaterialRequest, Notification, ReassignmentProposal, Referral, ServiceRequest, WorkOrder,
)
from app.modules.complaints.service import create_complaint
from app.modules.referrals.service import send_referral
from app.modules.sla import engine
from app.seed import build, geo
from tests.test_api_flow import login


@pytest.fixture
def seeded(db):
    build.rng.seed(2026)
    build.Seeder(db).run()
    db.commit()
    registry.register_agents()
    from app.core.bus import bus

    bus.subscribe("complaint.reopened", engine.on_reopened)
    return db


def atrisk_job(db) -> WorkOrder:
    return db.scalar(select(WorkOrder).where(WorkOrder.crew_id == "W12-B", WorkOrder.status == "ASSIGNED",
                                             WorkOrder.est_cost_inr == 7500))


def test_at_risk_overloaded_crew_and_no_material(seeded):
    db = seeded
    wo = atrisk_job(db)
    sr = db.get(ServiceRequest, wo.sr_id)
    engine.sweep(db)
    db.commit()
    assert db.scalar(select(ReassignmentProposal)) is None  # 70%: still on track
    clock.advance(timedelta(hours=6, minutes=5))  # -> 75%
    engine.sweep(db)
    db.commit()
    db.expire_all()
    run = db.scalar(select(AgentRun).where(AgentRun.agent == "followup", AgentRun.subject_id == sr.id))
    assert run is not None and run.output["situation"] == "AT_RISK"
    assert set(run.output["diagnosis"]) >= {"CREW_OVERLOAD", "MATERIAL_OUT"}
    assert "crew W12-B has 6 open jobs for 4 slots" in run.output["explanation"]
    assert "cold-mix bitumen is out of stock since 02 Nov" in run.output["explanation"]
    p = db.scalar(select(ReassignmentProposal).where(ReassignmentProposal.wo_id == wo.id))
    assert p.to_crew_id == "W13-B" and p.status == "PENDING" and p.distance_km == 1.2
    assert db.scalar(select(MaterialRequest).where(MaterialRequest.sr_id == sr.id)).item == "cold_mix_bitumen"
    delay = db.scalar(select(Notification).where(Notification.related_sr_id == sr.id, Notification.event == "DELAY"))
    assert "out of stock" in delay.body and delay.recipient_type == "CITIZEN"
    assert wo.crew_id == "W12-B"  # nothing moves until an officer approves

    off = login(TestClient(app), "officer.w12")
    pending = off.get("/api/v1/reassignments").json()
    assert [x["id"] for x in pending] == [p.id]
    assert login(TestClient(app), "officer.w13").get("/api/v1/reassignments").json() == []  # other ward
    assert off.post(f"/api/v1/reassignments/{p.id}/approve", json={}).status_code == 200
    db.expire_all()
    assert db.get(WorkOrder, wo.id).crew_id == "W13-B"


def test_bescom_followups_then_l2_escalation_then_reply(seeded):
    db = seeded
    sr = create_complaint(db, category="STREETLIGHT", description="Streetlight not working at the bus stand, very dark",
                          lat=geo.STREETLIGHT_DEMO_SR[0], lon=geo.STREETLIGHT_DEMO_SR[1], contact_phone="9822222222")
    db.commit()
    ref = db.scalar(select(Referral).where(Referral.sr_id == sr.id))
    assert ref.agency == "BESCOM"
    send_referral(db, ref)
    db.commit()
    run_followup_timer()
    db.expire_all()
    assert db.get(Referral, ref.id).followups_sent == 0  # not due yet
    for n in (1, 2):
        clock.advance(timedelta(hours=24, minutes=1))
        run_followup_timer()
        db.expire_all()
        assert db.get(Referral, ref.id).followups_sent == n
    sr = db.get(ServiceRequest, sr.id)
    assert sr.escalation_level == 2
    e = db.scalar(select(Escalation).where(Escalation.sr_id == sr.id, Escalation.trigger == "AGENCY_NO_RESPONSE"))
    assert "followed up 2 times with no response" in e.reason_summary and "Not municipal inaction" in e.reason_summary
    msgs = [n.body for n in db.scalars(select(Notification).where(Notification.related_sr_id == sr.id, Notification.event == "DELAY"))]
    assert any("BESCOM" in m for m in msgs)
    # the officer plays BESCOM in the simulated Agency Inbox
    off = login(TestClient(app), "officer.w12")
    inbox = off.get("/api/v1/agency/inbox").json()
    assert inbox[0]["followups_sent"] == 2 and sum(m["direction"] == "OUT" for m in inbox[0]["messages"]) == 3
    off.post(f"/api/v1/agency/referrals/{ref.id}/reply", json={"status": "IN_PROGRESS", "message": "Feeder F-KGR-07 repair scheduled tomorrow"})
    clock.advance(timedelta(hours=30))
    run_followup_timer()
    db.expire_all()
    assert db.get(Referral, ref.id).followups_sent == 2  # no more chasing after a reply


def test_breach_reason_written_on_escalation(seeded):
    db = seeded
    wo = atrisk_job(db)
    clock.advance(timedelta(hours=37))  # 84 + 37 > 120 h
    engine.sweep(db)
    db.commit()
    db.expire_all()
    e = db.scalar(select(Escalation).where(Escalation.sr_id == wo.sr_id).order_by(Escalation.id.desc()))
    assert e.level == 1 and e.trigger == "SLA_BREACH"
    assert e.reason_summary.startswith("Delayed because") and "out of stock" in e.reason_summary
    assert db.get(ServiceRequest, wo.sr_id).sla_due_at == wo.assigned_at - timedelta(hours=4) + timedelta(hours=120)


def test_followup_falls_back_when_llm_errors(seeded, monkeypatch):
    from app.agents.followup import followup
    from app.agents.runtime.loop import run_agent

    class Boom:
        def available(self):
            return True

        def create(self, **kw):
            raise RuntimeError("API down")

    db = seeded
    wo = atrisk_job(db)
    monkeypatch.setattr("app.agents.runtime.loop.llm", Boom())
    from app.core.db import SessionLocal

    rid = run_agent(followup, "sla.at_risk", {"_event": "sla.at_risk", "id": wo.sr_id})
    s = SessionLocal()
    r = s.get(AgentRun, rid)
    assert r.status == "FALLBACK" and r.model == "rules" and r.output["reassign_to_crew"] == "W13-B"
    s.close()
