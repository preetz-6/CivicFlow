from datetime import timedelta

from app.core.actor import Actor
from app.core.bus import bus
from app.core.clock import clock
from app.models import Escalation
from app.modules.sla import engine
from app.modules.sla.service import compute
from app.modules.workflow.service import transition
from tests.factories import make_sr


def test_states_with_frozen_time(db, world):
    sr = make_sr(db, world, status="ASSIGNED")  # 120 h SLA from T0
    assert compute(sr).state == "ON_TRACK"
    clock.advance(timedelta(hours=89))
    assert compute(sr).state == "ON_TRACK"
    clock.advance(timedelta(hours=1))  # 90/120 = 75%
    assert compute(sr).state == "AT_RISK"
    clock.advance(timedelta(hours=31))
    v = compute(sr)
    assert v.state == "BREACHED" and v.label == "Breached by 1h 0m"


def test_pause_excluded_from_elapsed(db, world):
    off = Actor.from_user(world.officer12)
    sr = make_sr(db, world, status="ASSIGNED")
    clock.advance(timedelta(hours=80))
    transition(db, sr, "ON_HOLD", off, hold_reason="AGENCY")
    clock.advance(timedelta(hours=100))
    assert compute(sr).state == "PAUSED"
    transition(db, sr, "ASSIGNED", off)
    v = compute(sr)
    assert v.state == "ON_TRACK" and round(v.fraction, 3) == round(80 / 120, 3)


def test_breach_escalates_without_resetting_clock(db, world):
    sr = make_sr(db, world, status="ASSIGNED")
    due, start = sr.sla_due_at, sr.sla_started_at
    seen = []
    bus.subscribe("sla.breached", lambda ev: seen.append(ev.payload["id"]))
    clock.advance(timedelta(hours=121))
    engine.sweep(db)
    db.commit()
    assert sr.escalation_level == 1 and sr.sla_state == "BREACHED" and seen == [sr.id]
    assert (sr.sla_due_at, sr.sla_started_at) == (due, start)
    engine.sweep(db)  # idempotent at the same time
    assert sr.escalation_level == 1
    clock.advance(timedelta(hours=60))  # +50% of 120 h overdue -> L2
    engine.sweep(db)
    assert sr.escalation_level == 2
    assert (sr.sla_due_at, sr.sla_started_at) == (due, start)
    clock.advance(timedelta(hours=1000))
    for _ in range(5):
        engine.sweep(db)
    assert sr.escalation_level == 4  # capped
    assert db.query(Escalation).filter_by(sr_id=sr.id).count() == 4


def test_at_risk_event_published_once(db, world):
    sr = make_sr(db, world, status="ASSIGNED")
    seen = []
    bus.subscribe("sla.at_risk", lambda ev: seen.append(ev.payload["id"]))
    clock.advance(timedelta(hours=95))
    engine.sweep(db)
    db.commit()
    engine.sweep(db)
    db.commit()
    assert seen == [sr.id]


def test_auto_close_after_verification_window(db, world):
    sr = make_sr(db, world, status="RESOLVED")
    sr.verification_due_at = clock.now() + timedelta(days=7)
    engine.sweep(db)
    assert sr.status == "RESOLVED"
    clock.advance(timedelta(days=7, minutes=1))
    engine.sweep(db)
    assert sr.status == "CLOSED" and sr.closure_type == "AUTO"


def test_second_reopen_escalates_to_l2(db, world):
    bus.subscribe("complaint.reopened", engine.on_reopened)
    cit = Actor.from_user(world.citizen)
    sr = make_sr(db, world, status="RESOLVED")
    transition(db, sr, "REOPENED", cit, reopen_reason="still broken")
    db.commit()
    db.refresh(sr)
    assert sr.escalation_level == 0
    sr.status = "RESOLVED"  # (shortcut: pretend it was fixed again)
    db.commit()
    transition(db, sr, "REOPENED", cit, reopen_reason="broken again")
    db.commit()
    db.refresh(sr)
    assert sr.escalation_level == 2
