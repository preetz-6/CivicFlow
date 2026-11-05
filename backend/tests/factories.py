"""Tiny test world: two wards (W12, W7), one officer each, a crew, a citizen, control room."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from itertools import count

from geoalchemy2.shape import from_shape
from shapely.geometry import MultiPolygon, Point, box

from app.core.actor import Actor
from app.core.clock import now
from app.models import (
    Attachment, Crew, Department, ServiceRequest, SlaPolicy, User, Ward, WorkOrder,
)

_n = count(1)
TEST_PASSWORD = "Test@1234"

W12_BOX = box(77.47, 12.90, 77.50, 12.93)
W7_BOX = box(77.50, 12.90, 77.53, 12.93)
W12_PT = (12.915, 77.485)  # lat, lon
W7_PT = (12.915, 77.515)


def pt(lat: float, lon: float):
    return from_shape(Point(lon, lat), srid=4326)


@dataclass
class World:
    officer12: User
    officer7: User
    control: User
    citizen: User
    citizen2: User
    field12: User
    field7: User
    crew12: Crew
    crew7: Crew

    def a(self, u: User) -> Actor:
        return Actor.from_user(u)


def make_world(db) -> World:
    db.add_all([
        Ward(id="W12", name="Kengeri", zone="West-1", geom=from_shape(MultiPolygon([W12_BOX]), srid=4326)),
        Ward(id="W7", name="Seven", zone="West-2", geom=from_shape(MultiPolygon([W7_BOX]), srid=4326)),
        Department(id="ROADS", name="Roads"),
    ])
    db.flush()
    db.add_all([
        Crew(id="W12-A", name="Crew W12-A", ward_id="W12", skills=["ROADS"], capacity=4, base_location=pt(*W12_PT)),
        Crew(id="W7-A", name="Crew W7-A", ward_id="W7", skills=["ROADS"], capacity=4, base_location=pt(*W7_PT)),
        SlaPolicy(category="POTHOLE", priority="P2", resolution_hours=120, verification_hours=168),
        SlaPolicy(category="POTHOLE", priority="P3", resolution_hours=168, verification_hours=168),
    ])
    db.flush()
    users = dict(
        officer12=User(username="officer.w12", name="Officer 12", role="WARD_OFFICER", ward_id="W12", zone="West-1", department_id="ROADS"),
        officer7=User(username="officer.w7", name="Officer 7", role="WARD_OFFICER", ward_id="W7", zone="West-2", department_id="ROADS"),
        control=User(username="control", name="Control", role="CONTROL_ROOM"),
        citizen=User(username="citizen1", name="Citizen One", role="CITIZEN", phone="9000000001", language="kn"),
        citizen2=User(username="citizen2", name="Citizen Two", role="CITIZEN", phone="9000000002"),
        field12=User(username="field.w12a", name="Field 12", role="FIELD_TEAM", crew_id="W12-A", ward_id="W12"),
        field7=User(username="field.w7a", name="Field 7", role="FIELD_TEAM", crew_id="W7-A", ward_id="W7"),
    )
    from app.core.security import hash_password

    for u in users.values():
        u.password_hash = hash_password(TEST_PASSWORD, iterations=1000)  # fast in tests
    db.add_all(users.values())
    db.flush()
    return World(**users, crew12=db.get(Crew, "W12-A"), crew7=db.get(Crew, "W7-A"))


def make_sr(db, world: World, status: str = "SUBMITTED", ward: str = "W12", **kw) -> ServiceRequest:
    n = next(_n)
    lat, lon = W12_PT if ward == "W12" else W7_PT
    t = now()
    sr = ServiceRequest(
        id=f"SR-2026-T{n:05d}", tracking_code=f"TRK{n:05d}", category=kw.pop("category", "POTHOLE"),
        description=kw.pop("description", "Big pothole near the school gate"), location=pt(lat, lon),
        ward_id=ward, department_id="ROADS", status=status, priority=kw.pop("priority", "P2"),
        citizen_id=world.citizen.id, contact_phone="9000000001", sla_started_at=t,
        sla_due_at=t + timedelta(hours=120), sla_paused_total=timedelta(0), **kw,
    )
    db.add(sr)
    db.flush()
    return sr


def make_wo(db, world: World, sr: ServiceRequest, status: str = "ASSIGNED", crew: str = "W12-A", **kw) -> WorkOrder:
    n = next(_n)
    wo = WorkOrder(id=f"WO-2026-T{n:05d}", sr_id=sr.id, crew_id=crew, scope="Fill pothole", status=status,
                   assigned_at=now(), **kw)
    db.add(wo)
    db.flush()
    return wo


def add_after_photo(db, wo: WorkOrder, uploaded_at=None) -> Attachment:
    a = Attachment(wo_id=wo.id, kind="AFTER", path="x.jpg", sha256=f"{next(_n):064d}",
                   uploaded_at=uploaded_at or now())
    db.add(a)
    db.flush()
    return a
