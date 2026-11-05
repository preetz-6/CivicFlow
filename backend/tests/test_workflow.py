"""Workflow spec tests, parametrised straight from the transition table."""
from datetime import timedelta
from itertools import product

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError

from app.core.actor import Actor
from app.core.bus import bus
from app.core.clock import clock
from app.core.errors import Forbidden, InvalidTransition, MissingFields
from app.models import AuditLog, ServiceRequest, StatusEvent, Timeline
from app.models.enums import ActorKind, Role, SRStatus, WOStatus
from app.modules.workflow.service import transition
from app.modules.workflow.table import RULES, SR_RULES, WO_RULES
from tests.factories import add_after_photo, make_sr, make_wo

HUMAN_PREF = [Role.WARD_OFFICER, Role.CONTROL_ROOM, Role.CITIZEN, Role.FIELD_TEAM]


def actor_for(world, who) -> Actor:
    if who == ActorKind.AGENT:
        return Actor.agent("test")
    if who == ActorKind.SYSTEM:
        return Actor.system("test")
    return Actor.from_user({
        Role.WARD_OFFICER: world.officer12, Role.CONTROL_ROOM: world.control,
        Role.CITIZEN: world.citizen, Role.FIELD_TEAM: world.field12,
    }[who])


def pick_allowed(rule):
    for r in HUMAN_PREF + [ActorKind.AGENT, ActorKind.SYSTEM]:
        if r in rule.actors:
            return r
    raise AssertionError(rule)


def required_values(db, world, rule, wo=None):
    vals = {}
    for f in rule.requires:
        if f == "after_photo":
            add_after_photo(db, wo)
        elif f == "owner_id":
            vals[f] = world.officer12.id
        elif f == "department_id":
            vals[f] = "ROADS"
        elif f == "parent_sr_id":
            vals[f] = make_sr(db, world, status="ASSIGNED").id
        elif f == "hold_reason":
            vals[f] = "MATERIAL"
        elif f == "closure_type":
            vals[f] = "CITIZEN"
        else:
            vals[f] = "test value"
    return vals


def setup_obj(db, world, rule):
    if rule.obj == "SR":
        obj = make_sr(db, world, status=rule.from_)
        wo = None
    else:
        sr = make_sr(db, world, status="IN_PROGRESS")
        obj = wo = make_wo(db, world, sr, status=rule.from_)
    if rule.only_if_prev:
        obj.prev_status = rule.to
    return obj, wo


@pytest.mark.parametrize("rule", SR_RULES + WO_RULES, ids=lambda r: f"{r.obj}:{r.from_}->{r.to}")
def test_every_allowed_transition_works(db, world, rule):
    obj, wo = setup_obj(db, world, rule)
    vals = required_values(db, world, rule, wo)
    transition(db, obj, rule.to, actor_for(world, pick_allowed(rule)), **vals)
    db.commit()
    assert obj.status == rule.to
    ev = db.scalars(select(StatusEvent).where(StatusEvent.object_id == obj.id)).all()
    assert [(e.from_state, e.to_state) for e in ev] == [(rule.from_, rule.to)]
    assert db.scalar(select(AuditLog).where(AuditLog.object == f"{rule.obj}:{obj.id}")) is not None


SR_STATES = [s.value for s in SRStatus]
WO_STATES = [s.value for s in WOStatus]
FORBIDDEN = [("SR", a, b) for a, b in product(SR_STATES, SR_STATES) if a != b and ("SR", a, b) not in RULES] + [
    ("WO", a, b) for a, b in product(WO_STATES, WO_STATES) if a != b and ("WO", a, b) not in RULES
]


@pytest.mark.parametrize("obj_kind,from_,to", FORBIDDEN, ids=lambda x: str(x))
def test_forbidden_transitions_rejected(db, world, obj_kind, from_, to):
    if obj_kind == "SR":
        obj = make_sr(db, world, status=from_)
    else:
        obj = make_wo(db, world, make_sr(db, world, status="IN_PROGRESS"), status=from_)
    with pytest.raises(InvalidTransition):
        transition(db, obj, to, Actor.from_user(world.control))
    assert obj.status == from_


ROLE_CASES = [
    (rule, role)
    for rule in SR_RULES + WO_RULES
    for role in list(Role) + [ActorKind.AGENT, ActorKind.SYSTEM]
    if role not in rule.actors
]


@pytest.mark.parametrize("rule,who", ROLE_CASES, ids=lambda x: getattr(x, "to", str(x)))
def test_wrong_actor_rejected(db, world, rule, who):
    obj, wo = setup_obj(db, world, rule)
    vals = required_values(db, world, rule, wo)
    with pytest.raises(Forbidden):
        transition(db, obj, rule.to, actor_for(world, who), **vals)


def test_missing_required_field(db, world):
    sr = make_sr(db, world)
    with pytest.raises(MissingFields):
        transition(db, sr, "REJECTED", Actor.from_user(world.officer12), rejection_reason_code="DUP")


def test_wo_completion_requires_after_photo(db, world):
    sr = make_sr(db, world, status="IN_PROGRESS")
    wo = make_wo(db, world, sr, status="IN_PROGRESS", started_at=clock.now())
    with pytest.raises(MissingFields):
        transition(db, wo, "COMPLETED", Actor.from_user(world.field12))


def test_officer_cannot_touch_other_ward(db, world):
    sr = make_sr(db, world, ward="W12")
    with pytest.raises(Forbidden):
        transition(db, sr, "ASSIGNED", Actor.from_user(world.officer7), owner_id=world.officer7.id)


def test_field_team_cannot_touch_other_crew(db, world):
    sr = make_sr(db, world, status="ASSIGNED", ward="W7")
    wo = make_wo(db, world, sr, crew="W7-A")
    with pytest.raises(Forbidden):
        transition(db, wo, "IN_PROGRESS", Actor.from_user(world.field12))


def test_field_team_cannot_verify_own_work(db, world):
    sr = make_sr(db, world, status="WORK_COMPLETED")
    wo = make_wo(db, world, sr, status="COMPLETED")
    with pytest.raises(Forbidden):
        transition(db, wo, "VERIFIED", Actor.from_user(world.field12))


def test_full_cascade_wo_drives_sr(db, world):
    field, control = Actor.from_user(world.field12), Actor.from_user(world.control)
    sr = make_sr(db, world, status="ASSIGNED")
    wo = make_wo(db, world, sr)
    transition(db, wo, "IN_PROGRESS", field)
    assert sr.status == "IN_PROGRESS"
    clock.advance(timedelta(hours=1))
    add_after_photo(db, wo)
    transition(db, wo, "COMPLETED", field)
    assert sr.status == "WORK_COMPLETED"
    transition(db, wo, "REWORK", Actor.agent("auditor"), rework_reason="Photo 2 km away")
    assert sr.status == "IN_PROGRESS"
    transition(db, wo, "IN_PROGRESS", field)
    clock.advance(timedelta(hours=1))
    add_after_photo(db, wo)
    transition(db, wo, "COMPLETED", field)
    transition(db, wo, "VERIFIED", control)
    assert sr.status == "VERIFIED"
    db.commit()
    stages = [t.stage for t in db.scalars(select(Timeline).where(Timeline.sr_id == sr.id).order_by(Timeline.id))]
    assert "Sent for Rework" in stages and stages[-1] == "Work Verified"


def test_sr_waits_for_all_work_orders(db, world):
    field = Actor.from_user(world.field12)
    sr = make_sr(db, world, status="IN_PROGRESS")
    wo1 = make_wo(db, world, sr, status="IN_PROGRESS", started_at=clock.now())
    make_wo(db, world, sr, status="IN_PROGRESS", started_at=clock.now())
    add_after_photo(db, wo1)
    transition(db, wo1, "COMPLETED", field)
    assert sr.status == "IN_PROGRESS"


def test_hold_with_approved_reason_pauses_sla(db, world):
    off = Actor.from_user(world.officer12)
    sr = make_sr(db, world, status="ASSIGNED")
    transition(db, sr, "ON_HOLD", off, hold_reason="AGENCY")
    assert sr.sla_state == "PAUSED" and sr.prev_status == "ASSIGNED"
    clock.advance(timedelta(hours=10))
    with pytest.raises(InvalidTransition):
        transition(db, sr, "IN_PROGRESS", off)  # must resume to previous state
    transition(db, sr, "ASSIGNED", off)
    assert sr.sla_paused_total == timedelta(hours=10)
    assert sr.sla_paused_at is None


def test_hold_for_material_does_not_pause_sla(db, world):
    off = Actor.from_user(world.officer12)
    sr = make_sr(db, world, status="ASSIGNED")
    transition(db, sr, "ON_HOLD", off, hold_reason="MATERIAL")
    assert sr.sla_paused_at is None
    clock.advance(timedelta(hours=5))
    transition(db, sr, "ASSIGNED", off)
    assert sr.sla_paused_total == timedelta(0)


def test_event_published_only_after_commit(db, world):
    seen = []
    bus.subscribe("complaint.assigned", lambda ev: seen.append(ev.payload["id"]))
    sr = make_sr(db, world)
    transition(db, sr, "ASSIGNED", Actor.from_user(world.officer12), owner_id=world.officer12.id)
    assert seen == []
    db.commit()
    assert seen == [sr.id]


def test_event_dropped_on_rollback(db, world):
    seen = []
    bus.subscribe("complaint.assigned", lambda ev: seen.append(ev))
    sr = make_sr(db, world)
    db.commit()
    transition(db, sr, "ASSIGNED", Actor.from_user(world.officer12), owner_id=world.officer12.id)
    db.rollback()
    db.commit()
    assert seen == []


def test_audit_log_is_append_only(db, world):
    sr = make_sr(db, world)
    transition(db, sr, "ASSIGNED", Actor.from_user(world.officer12), owner_id=world.officer12.id)
    db.commit()
    for stmt in ("UPDATE audit_log SET actor = 'x'", "DELETE FROM status_events"):
        with pytest.raises(DBAPIError):
            db.execute(text(stmt))
        db.rollback()


def test_merge_by_agent_and_unmerge(db, world):
    parent = make_sr(db, world, status="ASSIGNED")
    dup = make_sr(db, world)
    transition(db, dup, "MERGED", Actor.agent("investigator"), parent_sr_id=parent.id)
    assert dup.parent_sr_id == parent.id and dup.sla_state == "STOPPED"
    transition(db, dup, "SUBMITTED", Actor.from_user(world.officer12), reason="Different pothole")
    assert dup.parent_sr_id is None


def test_reopen_counts(db, world):
    sr = make_sr(db, world, status="RESOLVED", closure_type=None)
    transition(db, sr, "REOPENED", Actor.from_user(world.citizen), reopen_reason="Still broken")
    assert sr.reopen_count == 1
    db.commit()
    assert db.get(ServiceRequest, sr.id).status == "REOPENED"


def test_bus_waits_for_outer_commit_not_savepoint_release(db, world):
    seen = []
    bus.subscribe("x.inner", lambda ev: seen.append(ev.name))
    with db.begin_nested():
        bus.publish(db, "x.inner", {})
    assert seen == []  # savepoint released: other sessions can't see the data yet
    db.commit()
    assert seen == ["x.inner"]


def test_bus_savepoint_rollback_drops_only_its_own_events(db, world):
    seen = []
    bus.subscribe("x.kept", lambda ev: seen.append(ev.name))
    bus.subscribe("x.dropped", lambda ev: seen.append(ev.name))
    bus.publish(db, "x.kept", {})
    try:
        with db.begin_nested():
            bus.publish(db, "x.dropped", {})
            raise RuntimeError("tool failed")
    except RuntimeError:
        pass
    db.commit()
    assert seen == ["x.kept"]
