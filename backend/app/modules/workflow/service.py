"""transition(): the only function that changes an SR or WO status.

It (1) locks the row, (2) finds the rule or raises InvalidTransition,
(3) checks the actor's role, scope and required fields, (4) applies the
state and fields, (5) writes status_events + audit_log (+ citizen timeline),
(6) publishes `complaint.<state>` / `work_order.<state>`, and (7) cascades
work-order changes up to the parent complaint (as SYSTEM).
"""
from __future__ import annotations

from datetime import timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core import scope
from app.core.actor import Actor
from app.core.bus import bus
from app.core.clock import now
from app.core.errors import Forbidden, InvalidTransition, MissingFields
from app.models import Attachment, AuditLog, ServiceRequest, StatusEvent, Timeline, WorkOrder
from app.models.enums import (
    SLA_PAUSE_REASONS, ActorKind, AttachmentKind, HoldReason, SLAState, SRStatus, WOStatus,
)
from app.modules.workflow.remarks import SR_REMARKS, WO_REMARKS
from app.modules.workflow.table import allowed_targets, find_rule

AUDITED_FIELDS = (
    "status", "prev_status", "hold_reason", "owner_id", "department_id", "ward_id", "priority",
    "category", "parent_sr_id", "closure_type", "escalation_level", "crew_id", "rework_reason",
    "rejection_reason_code", "sla_state",
)
# kwargs that are recorded on the status event but are not columns
NON_COLUMN_FIELDS = {"reason", "reopen_reason", "after_photo"}


def _kind(obj) -> str:
    if isinstance(obj, ServiceRequest):
        return "SR"
    if isinstance(obj, WorkOrder):
        return "WO"
    raise TypeError(f"transition() does not handle {type(obj).__name__}")


def _snapshot(obj) -> dict[str, Any]:
    return {f: _jsonable(getattr(obj, f)) for f in AUDITED_FIELDS if hasattr(obj, f)}


def _jsonable(v):
    if v is None or isinstance(v, (str, int, float, bool)):
        return v
    return str(v)


def _has_after_photo(db: Session, wo: WorkOrder) -> bool:
    q = select(func.count()).select_from(Attachment).where(
        Attachment.wo_id == wo.id, Attachment.kind == AttachmentKind.AFTER
    )
    if wo.started_at is not None:
        q = q.where(Attachment.uploaded_at >= wo.started_at)
    return (db.scalar(q) or 0) > 0


def _check_actor(rule, actor: Actor) -> None:
    if actor.kind == ActorKind.HUMAN:
        if actor.role not in rule.actors:
            raise Forbidden(
                f"Role {actor.role} cannot move {rule.obj} from {rule.from_} to {rule.to}",
                allowed=sorted(str(a) for a in rule.actors),
            )
    elif actor.kind not in rule.actors:
        raise Forbidden(f"{actor.kind} actors cannot move {rule.obj} from {rule.from_} to {rule.to}")


def _check_scope(db: Session, actor: Actor, kind: str, obj) -> None:
    if not actor.is_human:
        return
    if kind == "SR":
        scope.ensure_sr(db, actor, obj.id)
    else:
        scope.ensure_wo(db, actor, obj.id)


def transition(
    db: Session,
    obj: ServiceRequest | WorkOrder,
    to: str,
    actor: Actor,
    *,
    reason: str | None = None,
    public_remark: str | None = None,
    public_remark_kn: str | None = None,
    meta: dict | None = None,
    scope_verified: bool = False,
    **fields: Any,
):
    kind = _kind(obj)
    to = str(to)
    db.flush()
    # Row lock: a stale agent action (e.g. auto-merge after an officer accepted) fails cleanly.
    db.execute(
        select(type(obj)).where(type(obj).id == obj.id).with_for_update().execution_options(populate_existing=True)
    )
    from_ = obj.status

    rule = find_rule(kind, from_, to)
    if rule is None:
        raise InvalidTransition(
            f"{kind} {obj.id}: {from_} -> {to} is not allowed", allowed=allowed_targets(kind, from_)
        )
    _check_actor(rule, actor)
    if not scope_verified:  # anonymous citizens are verified by tracking code in the router
        _check_scope(db, actor, kind, obj)
    if rule.only_if_prev and obj.prev_status != to:
        raise InvalidTransition(f"{kind} {obj.id} can only resume to {obj.prev_status}")

    if reason is not None and "reason" not in fields:
        fields["reason"] = reason
    missing = []
    for f in rule.requires:
        if f == "after_photo":
            if kind == "WO" and not _has_after_photo(db, obj):
                missing.append(f)
            continue
        if fields.get(f) in (None, "") and getattr(obj, f, None) in (None, ""):
            missing.append(f)
    if missing:
        raise MissingFields(f"Missing required fields for {from_} -> {to}: {', '.join(missing)}", missing=missing)
    if "hold_reason" in fields and fields["hold_reason"] not in HoldReason.__members__:
        raise MissingFields(f"hold_reason must be one of {', '.join(HoldReason)}")

    before = _snapshot(obj)
    t = now()

    for k, v in fields.items():
        if k in NON_COLUMN_FIELDS:
            continue
        if not hasattr(obj, k):
            raise MissingFields(f"Unknown field {k}")
        setattr(obj, k, v)

    _on_exit(obj, kind, from_, t)
    obj.status = to
    _on_enter(obj, kind, from_, to, actor, t)

    ev_meta = dict(meta or {})
    for k in ("reopen_reason", "hold_reason", "parent_sr_id", "closure_type", "rework_reason"):
        if fields.get(k):
            ev_meta[k] = _jsonable(fields[k])
    db.add(
        StatusEvent(
            object_type=kind, object_id=obj.id, from_state=from_, to_state=to, actor_type=str(actor.kind),
            actor=actor.id, actor_label=actor.label, reason=fields.get("reason") or fields.get("reopen_reason"),
            meta=ev_meta or None, at=t,
        )
    )
    db.add(
        AuditLog(
            actor=actor.id, action=f"{kind}.transition.{from_}->{to}", object=f"{kind}:{obj.id}",
            before_json=before, after_json=_snapshot(obj), at=t,
        )
    )
    _timeline(db, kind, obj, to, actor, t, public_remark, public_remark_kn, fields)

    name = ("complaint." if kind == "SR" else "work_order.") + to.lower()
    payload = {"id": obj.id, "from": from_, "to": to, "actor": actor.id}
    if kind == "WO":
        payload["sr_id"] = obj.sr_id
    bus.publish(db, name, payload)

    if kind == "WO":
        _cascade_wo(db, obj, to, actor)
    return obj


def _on_exit(obj, kind: str, from_: str, t) -> None:
    if from_ == "ON_HOLD":
        if kind == "SR" and obj.sla_paused_at is not None:
            obj.sla_paused_total = (obj.sla_paused_total or timedelta(0)) + (t - obj.sla_paused_at)
            obj.sla_paused_at = None
            obj.sla_state = None  # recomputed by the SLA sweep
        obj.hold_reason = None
        obj.prev_status = None


def _on_enter(obj, kind: str, from_: str, to: str, actor: Actor, t) -> None:
    if to == "ON_HOLD":
        obj.prev_status = from_
        if kind == "SR" and obj.hold_reason in SLA_PAUSE_REASONS and obj.sla_paused_at is None:
            obj.sla_paused_at = t
            obj.sla_state = SLAState.PAUSED
    if kind == "SR":
        if to in (SRStatus.CLOSED, SRStatus.REJECTED, SRStatus.MERGED):
            obj.sla_state = SLAState.STOPPED
        if to == SRStatus.CLOSED:
            obj.closed_at = t
        if to == SRStatus.RESOLVED:
            obj.resolved_at = t
        if to == SRStatus.REOPENED:
            obj.reopen_count = (obj.reopen_count or 0) + 1
            obj.closure_type = None
        if to == SRStatus.SUBMITTED and from_ == SRStatus.MERGED:
            obj.parent_sr_id = None
            obj.sla_state = None
    else:
        if to == WOStatus.IN_PROGRESS and obj.started_at is None:
            obj.started_at = t
        if to == WOStatus.COMPLETED:
            obj.completed_at = t
        if to == WOStatus.REWORK:
            obj.rework_count = (obj.rework_count or 0) + 1
        if to == WOStatus.VERIFIED:
            obj.verified_by = actor.user_id
            obj.verified_at = t


def _timeline(db, kind, obj, to, actor, t, remark, remark_kn, fields) -> None:
    table = SR_REMARKS if kind == "SR" else WO_REMARKS
    default = table.get(to)
    if default is None and remark is None:
        return
    stage, en, kn = default or (to.title(), "", "")
    if kind == "SR" and to == "REJECTED" and fields.get("rejection_explanation"):
        en = f"{en} Reason: {fields['rejection_explanation']}"
    if kind == "SR" and to == "ON_HOLD" and fields.get("hold_reason"):
        en = f"{en} Reason: {str(fields['hold_reason']).title()}."
    db.add(
        Timeline(
            sr_id=obj.id if kind == "SR" else obj.sr_id, stage=stage, remarks=remark or en,
            remarks_kn=remark_kn or kn, actor_type=str(actor.kind), at=t,
        )
    )


def _cascade_wo(db: Session, wo: WorkOrder, to: str, actor: Actor) -> None:
    sr = db.get(ServiceRequest, wo.sr_id)
    if sr is None:
        return
    sys = Actor.system("workflow")
    siblings = db.scalars(select(WorkOrder).where(WorkOrder.sr_id == sr.id)).all()
    statuses = {w.status for w in siblings}

    if to == WOStatus.IN_PROGRESS:
        if sr.status == SRStatus.ASSIGNED:
            transition(db, sr, SRStatus.IN_PROGRESS, sys)
        elif sr.status == SRStatus.WORK_COMPLETED:  # restarting after rework
            transition(db, sr, SRStatus.IN_PROGRESS, sys)
    elif to == WOStatus.COMPLETED:
        if sr.status == SRStatus.IN_PROGRESS and statuses <= {WOStatus.COMPLETED, WOStatus.VERIFIED}:
            transition(db, sr, SRStatus.WORK_COMPLETED, sys)
    elif to == WOStatus.REWORK:
        if sr.status == SRStatus.WORK_COMPLETED:
            transition(db, sr, SRStatus.IN_PROGRESS, sys)
    elif to == WOStatus.VERIFIED:
        if sr.status == SRStatus.WORK_COMPLETED and statuses == {WOStatus.VERIFIED}:
            transition(db, sr, SRStatus.VERIFIED, actor)


def next_sr_id(db: Session) -> str:
    n = db.scalar(select(func.nextval("sr_seq")))
    return f"SR-{now().year}-{n:06d}"


def next_wo_id(db: Session) -> str:
    n = db.scalar(select(func.nextval("wo_seq")))
    return f"WO-{now().year}-{n:06d}"
