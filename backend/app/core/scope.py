"""Authorization lives here, next to the data, never only in the UI.

Ward officer -> own ward only. Field team -> own crew's work orders only.
Citizen -> own complaints (or ones they were merged into). Control room -> city-wide.
"""
from __future__ import annotations

from sqlalchemy import Select, exists, or_, select
from sqlalchemy.orm import Session

from app.core.actor import Actor
from app.core.errors import Forbidden
from app.models import ServiceRequest, SrReporter, WorkOrder
from app.models.enums import ActorKind, Role


def scope_srs(q: Select, actor: Actor) -> Select:
    if actor.kind != ActorKind.HUMAN or actor.role == Role.CONTROL_ROOM:
        return q
    if actor.role == Role.WARD_OFFICER:
        return q.where(ServiceRequest.ward_id == actor.ward_id)
    if actor.role == Role.CITIZEN:
        return q.where(
            or_(
                ServiceRequest.citizen_id == actor.user_id,
                exists().where(SrReporter.sr_id == ServiceRequest.id, SrReporter.citizen_user_id == actor.user_id),
            )
        )
    if actor.role == Role.FIELD_TEAM:
        return q.where(
            exists().where(WorkOrder.sr_id == ServiceRequest.id, WorkOrder.crew_id == actor.crew_id)
        )
    return q.where(False)


def scope_wos(q: Select, actor: Actor) -> Select:
    if actor.kind != ActorKind.HUMAN or actor.role == Role.CONTROL_ROOM:
        return q
    if actor.role == Role.FIELD_TEAM:
        return q.where(WorkOrder.crew_id == actor.crew_id)
    if actor.role == Role.WARD_OFFICER:
        return q.join(ServiceRequest, ServiceRequest.id == WorkOrder.sr_id).where(
            ServiceRequest.ward_id == actor.ward_id
        )
    return q.where(False)


def can_access_sr(db: Session, actor: Actor, sr_id: str) -> bool:
    return db.scalar(scope_srs(select(ServiceRequest.id).where(ServiceRequest.id == sr_id), actor)) is not None


def can_access_wo(db: Session, actor: Actor, wo_id: str) -> bool:
    return db.scalar(scope_wos(select(WorkOrder.id).where(WorkOrder.id == wo_id), actor)) is not None


def ensure_sr(db: Session, actor: Actor, sr_id: str) -> None:
    if not can_access_sr(db, actor, sr_id):
        raise Forbidden("You do not have access to this grievance")


def ensure_wo(db: Session, actor: Actor, wo_id: str) -> None:
    if not can_access_wo(db, actor, wo_id):
        raise Forbidden("You do not have access to this work order")


def can_see_contact(actor: Actor) -> bool:
    """Field teams never see the citizen's phone number."""
    return actor.kind != ActorKind.HUMAN or actor.role in (Role.WARD_OFFICER, Role.CONTROL_ROOM)
