"""The ONE declarative transition table (brief §6.1 / §6.2).

Each row says: object type, from-state, to-state, who may do it, and which
fields must be present. `transition()` in service.py is the only code that
changes a status, and it reads only this table.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from app.models.enums import ActorKind, Role
from app.models.enums import SRStatus as S
from app.models.enums import WOStatus as W

OFFICER = frozenset({Role.WARD_OFFICER, Role.CONTROL_ROOM})
CONTROL = frozenset({Role.CONTROL_ROOM})
CITIZEN = frozenset({Role.CITIZEN})
FIELD = frozenset({Role.FIELD_TEAM})
AGENT = ActorKind.AGENT
SYSTEM = ActorKind.SYSTEM


@dataclass(frozen=True)
class Rule:
    obj: str  # "SR" | "WO"
    from_: str
    to: str
    actors: frozenset  # Roles for humans, ActorKind.AGENT / SYSTEM for non-humans
    requires: tuple[str, ...] = ()
    note: str = ""
    only_if_prev: bool = False  # ON_HOLD -> X allowed only if prev_status == X
    meta: dict = field(default_factory=dict, compare=False, hash=False)


def _r(obj, from_, to, actors, requires=(), note="", only_if_prev=False) -> Rule:
    return Rule(obj, str(from_), str(to), frozenset(actors), tuple(requires), note, only_if_prev)


SR_RULES = [
    _r("SR", S.SUBMITTED, S.ASSIGNED, OFFICER, ("owner_id", "department_id"), "Officer accepts the System Analysis brief"),
    _r("SR", S.SUBMITTED, S.MERGED, OFFICER | {AGENT}, ("parent_sr_id",), "Duplicate merged into parent"),
    _r("SR", S.SUBMITTED, S.REJECTED, OFFICER, ("rejection_reason_code", "rejection_explanation"), "Officer rejects"),
    _r("SR", S.ASSIGNED, S.IN_PROGRESS, {SYSTEM}, (), "First work order started"),
    _r("SR", S.ASSIGNED, S.ON_HOLD, OFFICER, ("hold_reason",)),
    _r("SR", S.IN_PROGRESS, S.ON_HOLD, OFFICER, ("hold_reason",)),
    _r("SR", S.ON_HOLD, S.ASSIGNED, OFFICER, (), "Resume", only_if_prev=True),
    _r("SR", S.ON_HOLD, S.IN_PROGRESS, OFFICER, (), "Resume", only_if_prev=True),
    _r("SR", S.IN_PROGRESS, S.WORK_COMPLETED, {SYSTEM}, (), "All work orders completed"),
    _r("SR", S.WORK_COMPLETED, S.IN_PROGRESS, {SYSTEM}, (), "A work order was sent for rework"),
    _r("SR", S.WORK_COMPLETED, S.VERIFIED, CONTROL, (), "All work orders verified"),
    _r("SR", S.VERIFIED, S.RESOLVED, {SYSTEM}, (), "Citizen notified with before/after photos"),
    _r("SR", S.RESOLVED, S.CLOSED, CITIZEN | {SYSTEM}, ("closure_type",), "Citizen confirmed / window expired"),
    _r("SR", S.RESOLVED, S.REOPENED, CITIZEN, ("reopen_reason",), "Citizen reopened"),
    _r("SR", S.REOPENED, S.ASSIGNED, OFFICER, ("owner_id",), "Re-assigned after re-investigation"),
    _r("SR", S.MERGED, S.SUBMITTED, OFFICER, ("reason",), "Unmerge"),
]

WO_RULES = [
    _r("WO", W.ASSIGNED, W.IN_PROGRESS, FIELD, (), "Field team started"),
    _r("WO", W.IN_PROGRESS, W.COMPLETED, FIELD, ("after_photo",), "Field team marked completed"),
    _r("WO", W.COMPLETED, W.REWORK, CONTROL | {AGENT}, ("rework_reason",), "Sent back for rework"),
    _r("WO", W.REWORK, W.IN_PROGRESS, FIELD, (), "Rework started"),
    _r("WO", W.COMPLETED, W.VERIFIED, CONTROL, (), "Verified by Control Room / EE"),
    _r("WO", W.ASSIGNED, W.ON_HOLD, OFFICER, ("hold_reason",)),
    _r("WO", W.IN_PROGRESS, W.ON_HOLD, OFFICER, ("hold_reason",)),
    _r("WO", W.ON_HOLD, W.ASSIGNED, OFFICER, (), "Resume", only_if_prev=True),
    _r("WO", W.ON_HOLD, W.IN_PROGRESS, OFFICER | FIELD, (), "Resume", only_if_prev=True),
]

RULES: dict[tuple[str, str, str], Rule] = {(r.obj, r.from_, r.to): r for r in SR_RULES + WO_RULES}


def find_rule(obj: str, from_: str, to: str) -> Rule | None:
    return RULES.get((obj, str(from_), str(to)))


def allowed_targets(obj: str, from_: str) -> list[str]:
    return [r.to for r in RULES.values() if r.obj == obj and r.from_ == str(from_)]
