"""Seed the demo city.  python -m app.seed.build [--reset] [--demo]

Deterministic: fixed RNG seed, fixed clock origin (DEMO_EPOCH), sequences restarted.
That determinism is what lets the agent replay cache hit during the demo.
"""
from __future__ import annotations

import argparse
import random
import string
from datetime import date, timedelta

from geoalchemy2.shape import from_shape
from shapely.geometry import Point
from sqlalchemy import text

import app.models  # noqa: F401
from app.config import settings
from app.core.clock import clock
from app.core.db import Base, SessionLocal
from app.core.security import hash_api_key, hash_password
from app.domain_config import (
    CATEGORY_DEPARTMENT, DEFAULT_RESOLUTION_HOURS, VERIFICATION_HOURS, resolution_hours,
)
from app.models import (
    Asset, AssetEvent, Crew, DataSource, Department, Inventory, KnownRoadFeature, PlannedWork,
    RoadSegment, SensitivePlace, ServiceRequest, SlaPolicy, StatusEvent, Timeline, User, Ward, WorkOrder,
)
from app.modules.system import clock_state
from app.modules.workflow.remarks import SR_REMARKS
from app.seed import geo

E = settings.demo_epoch
rng = random.Random(2026)


def H(h: float) -> timedelta:
    return timedelta(hours=h)


def D(d: float) -> timedelta:
    return timedelta(days=d)


def pt(lat: float, lon: float):
    return from_shape(Point(lon, lat), srid=4326)


def jitter(lat: float, lon: float, metres: float) -> tuple[float, float]:
    d = metres / 111_000
    return (round(lat + rng.uniform(-d, d), 6), round(lon + rng.uniform(-d, d), 6))


def random_point_in(ward_id: str) -> tuple[float, float]:
    while True:
        lat, lon = round(rng.uniform(12.881, 12.949), 6), round(rng.uniform(77.461, 77.549), 6)
        if geo.ward_of(lat, lon) == ward_id:
            return lat, lon


def nearest_landmark(lat: float, lon: float, max_m: float = 450) -> str | None:
    from app.modules.geo import distance_m

    name, d = min(((n, distance_m((lat, lon), p)) for n, _t, p in SENSITIVE), key=lambda x: x[1])
    return f"Near {name}" if d <= max_m else None


def tracking_code() -> str:
    return "".join(rng.choices(string.ascii_uppercase + string.digits, k=8))


# --------------------------------------------------------------------------------------------
DEPARTMENTS = [
    ("ROADS", "Roads & Infrastructure", "ರಸ್ತೆ ಮತ್ತು ಮೂಲಸೌಕರ್ಯ"),
    ("LIGHTING", "Street Lighting", "ಬೀದಿ ದೀಪ"),
    ("SWM", "Solid Waste Management", "ಘನತ್ಯಾಜ್ಯ ನಿರ್ವಹಣೆ"),
    ("SWD", "Storm Water Drains", "ಮಳೆನೀರು ಚರಂಡಿ"),
    ("WATER", "Water Supply Liaison (BWSSB)", "ನೀರು ಸರಬರಾಜು ಸಂಪರ್ಕ"),
    ("PARKS", "Parks & Trees", "ಉದ್ಯಾನ ಮತ್ತು ಮರಗಳು"),
]

# Initial staff passwords (one per role). Citizens have no login. Change them for any real deployment.
PASSWORDS = {"WARD_OFFICER": "Officer@2026", "FIELD_TEAM": "Field@2026",
             "CONTROL_ROOM": "Control@2026"}

USERS = [
    # username, name, role, designation, ward, zone, crew, lang, phone
    ("citizen1", "Lakshmi Narayan", "CITIZEN", "Citizen", None, None, None, "kn", "9845000001"),
    ("citizen2", "Rahul Gowda", "CITIZEN", "Citizen", None, None, None, "en", "9845000002"),
    ("citizen3", "Fatima Begum", "CITIZEN", "Citizen", None, None, None, "en", "9845000003"),
    ("officer.w12", "Suresh Kumar", "WARD_OFFICER", "Assistant Executive Engineer, Ward 12", "W12", "West Zone", None, "en", "9480000012"),
    ("officer.w13", "Anitha Rao", "WARD_OFFICER", "Assistant Executive Engineer, Ward 13", "W13", "West Zone", None, "en", "9480000013"),
    ("officer.w14", "Mohan Das", "WARD_OFFICER", "Assistant Executive Engineer, Ward 14", "W14", "West Zone", None, "en", "9480000014"),
    ("officer.w15", "Kavya Shetty", "WARD_OFFICER", "Assistant Executive Engineer, Ward 15", "W15", "West Zone", None, "en", "9480000015"),
    ("zonal.west", "Ramesh Hegde", "WARD_OFFICER", "Zonal Officer, West Zone", None, "West Zone", None, "en", "9480000100"),
    ("field.w12a", "Crew W12-A (Manjunath)", "FIELD_TEAM", "Field Supervisor, Crew W12-A", "W12", "West Zone", "W12-A", "kn", "9000001201"),
    ("field.w12b", "Crew W12-B (Imran)", "FIELD_TEAM", "Field Supervisor, Crew W12-B", "W12", "West Zone", "W12-B", "en", "9000001202"),
    ("field.w13a", "Crew W13-A (Prakash)", "FIELD_TEAM", "Field Supervisor, Crew W13-A", "W13", "West Zone", "W13-A", "kn", "9000001301"),
    ("field.w13b", "Crew W13-B (Joseph)", "FIELD_TEAM", "Field Supervisor, Crew W13-B", "W13", "West Zone", "W13-B", "en", "9000001302"),
    ("field.w14a", "Crew W14-A (Basavaraj)", "FIELD_TEAM", "Field Supervisor, Crew W14-A", "W14", "West Zone", "W14-A", "kn", "9000001401"),
    ("field.w15a", "Crew W15-A (Venkatesh)", "FIELD_TEAM", "Field Supervisor, Crew W15-A", "W15", "West Zone", "W15-A", "kn", "9000001501"),
    ("control", "Dr. K. Prakash", "CONTROL_ROOM", "Executive Engineer / Commissioner", None, None, None, "en", "9480000001"),
]

CREWS = [
    # id, ward, skills, capacity, base, contractor, target open-WO load
    ("W12-A", "W12", ["ROADS", "DRAINS"], 4, (12.9120, 77.4800), "Sri Manjunatha Constructions", 3),
    ("W12-B", "W12", ["ROADS", "ELECTRICAL"], 4, (12.9050, 77.4780), "Kengeri Civil Works", 6),
    ("W13-A", "W13", ["ROADS", "DRAINS"], 4, (12.9300, 77.5200), "RR Infra Services", 2),
    ("W13-B", "W13", ["ROADS", "ELECTRICAL"], 4, (12.9170, 77.5030), "RR Infra Services", 0),
    ("W14-A", "W14", ["ROADS", "DRAINS", "TREES"], 4, (12.9350, 77.4800), "Satellite Town Works", 1),
    ("W15-A", "W15", ["ROADS", "DRAINS", "SWM"], 4, (12.8950, 77.5200), "Hemmigepura Contractors", 2),
]

INVENTORY = [
    ("cold_mix_bitumen", "Cold-mix bitumen", 0, "tonne", E - D(3)),
    ("hot_mix_bitumen", "Hot-mix bitumen", 3.5, "tonne", None),
    ("led_driver_40w", "LED driver 40W", 0, "nos", E - D(2) - H(6)),  # out since 3 Nov
    ("led_luminaire_40w", "LED luminaire 40W", 22, "nos", None),
    ("streetlight_cable", "Streetlight supply cable", 400, "m", None),
    ("manhole_cover_ci", "Manhole cover (CI)", 14, "nos", None),
    ("desilting_kit", "Desilting kit", 6, "nos", None),
    ("jetting_machine", "Jetting machine (available)", 3, "nos", None),
]

SENSITIVE = [
    ("Govt. Higher Primary School, Kengeri", "SCHOOL", geo.SCHOOL),
    ("Kengeri TTMC Bus Stand", "BUS_STAND", geo.BUS_STAND),
    ("Kengeri Metro Station", "METRO", (12.9086, 77.4846)),
    ("Kengeri Govt. General Hospital", "HOSPITAL", (12.9120, 77.4800)),
    ("Kengeri Satellite Town Market", "MARKET", (12.9160, 77.4830)),
    ("Kengeri Satellite Town Bus Stop", "BUS_STAND", (12.9152, 77.4765)),
    ("St. Mary's High School, Satellite Town", "SCHOOL", (12.9330, 77.4790)),
    ("Kommaghatta Govt. School", "SCHOOL", (12.9258, 77.4660)),
    ("Satellite Town PHC", "HOSPITAL", (12.9400, 77.4850)),
    ("RR Nagar Arch Market", "MARKET", (12.9276, 77.5160)),
    ("RR Nagar Govt. PU College", "SCHOOL", (12.9230, 77.5210)),
    ("Ideal Homes Bus Stop", "BUS_STAND", (12.9212, 77.5300)),
    ("RR Nagar Maternity Home", "HOSPITAL", (12.9330, 77.5270)),
    ("BEML Layout Park", "PARK", (12.9405, 77.5180)),
    ("Pattanagere Metro Station", "METRO", (12.9195, 77.5098)),
    ("Rajarajeshwari Temple", "TEMPLE", (12.9265, 77.5205)),
    ("Hemmigepura Govt. School", "SCHOOL", (12.8860, 77.5050)),
    ("Channasandra Market", "MARKET", (12.8955, 77.5260)),
    ("SJB Institute of Technology", "SCHOOL", (12.8990, 77.4980)),
    ("BGS Global Hospital", "HOSPITAL", (12.8985, 77.4995)),
    ("Hemmigepura Bus Stop", "BUS_STAND", (12.8852, 77.5150)),
    ("Kengeri Hobli Anganwadi", "SCHOOL", (12.8930, 77.4700)),
    ("Uttarahalli Road Bus Stop", "BUS_STAND", (12.9051, 77.5150)),
    ("Halagevaderahalli Govt. School", "SCHOOL", (12.9350, 77.5300)),
]

PLANNED_WORKS = [
    ("Metro Phase-2 viaduct works (Mysore Road)", "BMRCL", geo.polygon_from_line(geo.MYSORE_ROAD[2:4]),
     date(2026, 6, 1), date(2027, 3, 31), "Barricading on median; lane narrowing."),
    ("Cauvery Stage-V pipeline laying (Uttarahalli Road)", "BWSSB", geo.polygon_from_line(geo.UTTARAHALLI_ROAD[1:3]),
     date(2026, 10, 15), date(2026, 12, 31), "Road cutting and restoration by BWSSB."),
    ("Underground HT cabling, RR Nagar 5th Main", "BESCOM", geo.polygon_from_line([(12.9300, 77.5050), (12.9300, 77.5300)]),
     date(2026, 11, 1), date(2027, 1, 15), "Trenching on footpath side."),
]

NAMES = [
    "Ravi Shankar", "Meena Kumari", "Arjun Reddy", "Shwetha N.", "Mohammed Irfan", "Deepa Prasad", "Kiran B.",
    "Savitha M.", "Naveen Kumar", "Priya Iyer", "Girish H.", "Nandini S.", "Abdul Rahman", "Sunitha Devi",
    "Harish Gowda", "Rekha P.", "Vinay K.", "Shabana T.", "Prakash Rao", "Anusha R.", "Manoj Kumar",
    "Bhavya L.", "Santosh Patil", "Roopa D.", "Yusuf Khan", "Chaitra G.", "Ganesh M.", "Lavanya S.",
]

CATEGORY_WEIGHTS = [
    ("POTHOLE", 26), ("STREETLIGHT", 20), ("GARBAGE", 18), ("DRAIN_BLOCKED", 10), ("WATER_LEAK", 8),
    ("DAMAGED_ROAD", 7), ("WATERLOGGING", 5), ("TREE_FALL", 3), ("OPEN_MANHOLE", 2), ("OTHER", 1),
]

DESCRIPTIONS = {
    "POTHOLE": ["Large pothole in the middle of the road, two-wheelers swerving.", "Deep pothole filled with water near the junction.",
                "Pothole has grown after last week's rain; vehicles getting damaged."],
    "DAMAGED_ROAD": ["Road surface broken for about 50 metres after pipeline work.", "Road edge has caved in near the drain."],
    "STREETLIGHT": ["Streetlight not working for the past week; the lane is completely dark.", "Three streetlights off in a row near the bus stop.",
                    "Streetlight flickering and switching off at night."],
    "GARBAGE": ["Garbage not collected for 4 days; dogs spreading it on the road.", "Black spot near the vacant site, garbage dumped every night."],
    "DRAIN_BLOCKED": ["Drain blocked with silt and plastic; water overflowing onto the road.", "Side drain choked, mosquito breeding."],
    "WATER_LEAK": ["Drinking water pipeline leaking for two days; water wasted on the road.", "Water leaking from a valve chamber."],
    "WATERLOGGING": ["Knee-deep water after rain; vehicles stuck.", "Underpass flooded, buses not able to pass."],
    "TREE_FALL": ["A large branch fell on the road and is blocking one lane.", "Tree uprooted after rain, resting on a compound wall."],
    "OPEN_MANHOLE": ["Manhole cover missing on the footpath, very dangerous at night."],
    "OTHER": ["Footpath slabs broken near the shop line."],
}


def pick_category() -> str:
    cats, weights = zip(*CATEGORY_WEIGHTS)
    return rng.choices(cats, weights=weights, k=1)[0]


# --------------------------------------------------------------------------------------------
def reset(db) -> None:
    tables = ", ".join(f'"{t.name}"' for t in Base.metadata.sorted_tables)
    db.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
    db.execute(text("ALTER SEQUENCE sr_seq RESTART WITH 1001"))
    db.execute(text("ALTER SEQUENCE wo_seq RESTART WITH 1001"))
    db.commit()


class Seeder:
    def __init__(self, db):
        self.db = db
        self.users: dict[str, User] = {}
        self.officer_of: dict[str, User] = {}
        self.policy: dict[tuple[str, str], SlaPolicy] = {}
        self.crew_load: dict[str, int] = {c[0]: 0 for c in CREWS}
        self.wo_n = 1000
        self.sr_n = 1000

    # ids are generated here (not via the sequences) and the sequences are moved past them
    def sr_id(self, created) -> str:
        self.sr_n += 1
        return f"SR-{created.year}-{self.sr_n:06d}"

    def wo_id(self, created) -> str:
        self.wo_n += 1
        return f"WO-{created.year}-{self.wo_n:06d}"

    def run(self) -> None:
        db = self.db
        self.reference()
        self.assets()
        self.history()
        self.repaired_spot()
        self.streetlight_context()
        self.atrisk_job()
        self.open_backlog()
        db.execute(text(f"SELECT setval('sr_seq', {self.sr_n})"))
        db.execute(text(f"SELECT setval('wo_seq', {self.wo_n})"))
        db.commit()

    # ---------------------------------------------------------------- reference data
    def reference(self) -> None:
        db = self.db
        for wid, name, name_kn, zone, g in geo.WARDS:
            db.add(Ward(id=wid, name=name, name_kn=name_kn, zone=zone, geom=from_shape(geo.as_multi(g), srid=4326)))
        for did, name, name_kn in DEPARTMENTS:
            db.add(Department(id=did, name=name, name_kn=name_kn))
        db.flush()
        for cid, ward, skills, cap, base, contractor, _ in CREWS:
            db.add(Crew(id=cid, name=f"Crew {cid}", ward_id=ward, skills=skills, capacity=cap,
                        base_location=pt(*base), contractor=contractor))
        db.flush()
        for un, name, role, desig, ward, zone, crew, lang, phone in USERS:
            u = User(username=un, name=name, role=role, designation=desig, ward_id=ward, zone=zone,
                     crew_id=crew, language=lang, phone=phone, created_at=E - D(120),
                     password_hash=hash_password(PASSWORDS[role]) if role in PASSWORDS else None)
            db.add(u)
            self.users[un] = u
            if role == "WARD_OFFICER" and ward:
                self.officer_of[ward] = u
        for item, name, qty, unit, out in INVENTORY:
            db.add(Inventory(item=item, name=name, qty=qty, unit=unit, out_since=out, updated_at=E - D(1)))
        for cat in CATEGORY_DEPARTMENT:
            for pr in DEFAULT_RESOLUTION_HOURS:
                p = SlaPolicy(category=cat, priority=pr, resolution_hours=resolution_hours(cat, pr),
                              verification_hours=VERIFICATION_HOURS[pr],
                              description=f"{cat.replace('_', ' ').title()} {pr}: resolve within {resolution_hours(cat, pr):g} h")
                db.add(p)
                self.policy[(cat, pr)] = p
        db.add(DataSource(id="oem-sim", name="Connected two-wheeler OEM feed", kind="VEHICLE_OEM",
                          api_key_hash=hash_api_key(settings.oem_sim_api_key), simulated=True))
        db.add(DataSource(id="citizen-photo", name="Citizen complaint photos", kind="CITIZEN_PHOTO",
                          api_key_hash=hash_api_key("internal-only-" + settings.secret_key), simulated=False))
        for name, typ, (lat, lon) in SENSITIVE:
            db.add(SensitivePlace(name=name, type=typ, location=pt(lat, lon)))
        for name, (lat, lon) in geo.SPEED_BREAKERS:
            db.add(KnownRoadFeature(type="SPEED_BREAKER", name=name, location=pt(lat, lon)))
        for name, (lat, lon) in geo.RAIL_CROSSINGS:
            db.add(KnownRoadFeature(type="RAIL_CROSSING", name=name, location=pt(lat, lon)))
        for name, pts in geo.ARTERIAL_ROADS:
            db.add(RoadSegment(name=name, road_class="ARTERIAL", geom=from_shape(geo.line(pts), srid=4326)))
        for name, pts in geo.LOCAL_ROADS:
            db.add(RoadSegment(name=name, road_class="LOCAL", geom=from_shape(geo.line(pts), srid=4326)))
        for name, agency, poly, start, end, note in PLANNED_WORKS:
            db.add(PlannedWork(name=name, agency=agency, geom=from_shape(poly, srid=4326), start=start, end=end, note=note))
        db.flush()

    # ---------------------------------------------------------------- assets
    def assets(self) -> None:
        db = self.db
        counters = {w[0]: 100 for w in geo.WARDS}
        roads = geo.ARTERIAL_ROADS + geo.LOCAL_ROADS
        n_lights = 0
        while n_lights < 117:
            _, pts = rng.choice(roads)
            lat, lon = geo.interp(pts, rng.random())
            ward = geo.ward_of(lat, lon)
            if not ward:
                continue
            counters[ward] += rng.randint(1, 9)
            aid = f"STREETLIGHT-{ward}-{counters[ward]:05d}"
            if db.get(Asset, aid):
                continue
            db.add(Asset(id=aid, type="STREETLIGHT", name="LED streetlight pole", location=pt(lat, lon), ward_id=ward,
                         owner="MUNICIPAL", condition=rng.choice(["OK"] * 8 + ["POOR"]), feeder=f"F-{ward}-{rng.randint(1, 9):02d}"))
            n_lights += 1
        # the demo pole and its feeder neighbours: BESCOM-maintained feeder F-KGR-07
        for n, (lat, lon) in [(870, (12.9085, 77.4836)), (871, geo.POLE_00871), (872, (12.9071, 77.4818))]:
            db.add(Asset(id=f"STREETLIGHT-W12-{n:05d}", type="STREETLIGHT", name="LED streetlight pole (bus stand stretch)",
                         location=pt(lat, lon), ward_id="W12", owner="BESCOM", condition="FAULTY" if n == 871 else "POOR",
                         feeder="F-KGR-07"))
        for i in range(30):
            ward = rng.choice(["W12", "W13", "W14", "W15"])
            lat, lon = random_point_in(ward)
            db.add(Asset(id=f"DRAIN-{ward}-{i + 1:04d}", type="DRAIN", name="Storm water drain segment", location=pt(lat, lon),
                         ward_id=ward, owner="MUNICIPAL", condition=rng.choice(["OK", "OK", "POOR"])))
        db.add(Asset(id="DRAIN-W12-UPASS", type="DRAIN", name="Kengeri underpass culvert", location=pt(*geo.KENGERI_UNDERPASS),
                     ward_id="W12", owner="MUNICIPAL", condition="POOR"))
        for i in range(10):
            ward = rng.choice(["W12", "W13", "W14", "W15"])
            lat, lon = random_point_in(ward)
            db.add(Asset(id=f"TRANSFORMER-{ward}-{i + 1:03d}", type="TRANSFORMER", name="Distribution transformer",
                         location=pt(lat, lon), ward_id=ward, owner="BESCOM", condition="OK"))
        for i in range(8):
            ward = rng.choice(["W12", "W13", "W14", "W15"])
            lat, lon = random_point_in(ward)
            db.add(Asset(id=f"WATERMAIN-{ward}-{i + 1:03d}", type="WATER_MAIN", name="Water distribution main",
                         location=pt(lat, lon), ward_id=ward, owner="BWSSB", condition="OK"))
        db.flush()
        pole = "STREETLIGHT-W12-00871"
        for dt, typ, note, crew in [
            (E - D(50), "COMPLAINT", "Citizen complaint: light not working near bus stand", None),
            (E - D(48), "REPAIR", "Replaced LED driver. Note: feeder F-KGR-07 voltage fluctuation suspected.", "W12-B"),
            (E - D(21), "COMPLAINT", "Citizen complaint: light off again", None),
            (E - D(19), "REPAIR", "Re-terminated supply cable; referred feeder check to BESCOM (no response).", "W12-B"),
        ]:
            db.add(AssetEvent(asset_id=pole, type=typ, date=dt, note=note, crew_id=crew))
        db.add(AssetEvent(asset_id="STREETLIGHT-W12-00870", type="REPAIR", date=E - D(33), note="Replaced luminaire", crew_id="W12-B"))
        db.flush()

    # ---------------------------------------------------------------- SR helpers
    def make_sr(self, *, category, lat, lon, created, status, priority=None, description=None, source="CITIZEN_WEB",
                citizen=None, contact=None, owner=True, **kw) -> ServiceRequest:
        ward = geo.ward_of(lat, lon)
        priority = priority or rng.choice(["P2", "P3", "P3", "P3", "P4"])
        pol = self.policy[(category, priority)]
        name, phone = contact or (rng.choice(NAMES), f"98{rng.randint(10_000_000, 99_999_999)}")
        sr = ServiceRequest(
            id=self.sr_id(created), tracking_code=tracking_code(), category=category, citizen_category=category,
            description=description or rng.choice(DESCRIPTIONS[category]), location=pt(lat, lon),
            address=nearest_landmark(lat, lon) if rng.random() < 0.4 else None,
            ward_id=ward, department_id=CATEGORY_DEPARTMENT[category], status=status, priority=priority,
            owner_id=self.officer_of[ward].id if owner and ward else None, source=source,
            sla_policy_id=pol.id, sla_started_at=created, sla_due_at=created + H(pol.resolution_hours),
            sla_paused_total=timedelta(0), citizen_id=citizen.id if citizen else None,
            contact_name=citizen.name if citizen else name, contact_phone=citizen.phone if citizen else phone,
            language=citizen.language if citizen else "en", created_at=created, updated_at=created, **kw,
        )
        self.db.add(sr)
        self.db.flush()
        return sr

    def history_rows(self, sr: ServiceRequest, steps: list[tuple[str, object, str]]) -> None:
        """steps: (to_state, at, actor_type)."""
        prev = None
        for to, at, actor_type in steps:
            self.db.add(StatusEvent(object_type="SR", object_id=sr.id, from_state=prev, to_state=to,
                                    actor_type=actor_type, actor=f"seed:{actor_type.lower()}", actor_label="Seed", at=at))
            stage, en, kn = SR_REMARKS.get(to, (to.title(), "", ""))
            self.db.add(Timeline(sr_id=sr.id, stage=stage, remarks=en, remarks_kn=kn, actor_type=actor_type, at=at))
            prev = to

    def make_wo(self, sr: ServiceRequest, crew: str, status: str, assigned_at, **kw) -> WorkOrder:
        wo = WorkOrder(id=self.wo_id(assigned_at), sr_id=sr.id, crew_id=crew, scope=kw.pop("scope", f"Attend {sr.category.lower().replace('_', ' ')}"),
                       root_cause=kw.pop("root_cause", None), est_cost_inr=kw.pop("est_cost_inr", rng.choice([3500, 6000, 8500, 12000])),
                       status=status, assigned_at=assigned_at, created_by=sr.owner_id, **kw)
        self.db.add(wo)
        if status in ("ASSIGNED", "IN_PROGRESS", "REWORK", "ON_HOLD"):
            self.crew_load[crew] += 1
        self.db.flush()
        return wo

    def crew_for(self, ward: str) -> str:
        return {"W12": "W12-A", "W13": "W13-A", "W14": "W14-A", "W15": "W15-A"}[ward]

    # ---------------------------------------------------------------- closed history (KPIs)
    def history(self) -> None:
        for _ in range(250):
            cat = pick_category()
            ward = rng.choice(["W12", "W12", "W13", "W13", "W14", "W15"])
            lat, lon = random_point_in(ward)
            created = E - D(rng.uniform(4, 90))
            pr = rng.choice(["P1"] * 1 + ["P2"] * 3 + ["P3"] * 5 + ["P4"])
            res_h = resolution_hours(cat, pr)
            r = rng.random()
            if r < 0.05:
                sr = self.make_sr(category=cat, lat=lat, lon=lon, created=created, status="REJECTED", priority=pr,
                                  rejection_reason_code="OUT_OF_JURISDICTION",
                                  rejection_explanation="This location is maintained by BMRCL; forwarded to them.",
                                  sla_state="STOPPED")
                self.history_rows(sr, [("SUBMITTED", created, "HUMAN"), ("REJECTED", created + H(5), "HUMAN")])
                continue
            if r < 0.11:
                sr = self.make_sr(category=cat, lat=lat, lon=lon, created=created, status="MERGED", priority=pr, sla_state="STOPPED")
                self.history_rows(sr, [("SUBMITTED", created, "HUMAN"), ("MERGED", created + H(0.2), "AGENT")])
                continue
            within = rng.random() < 0.78
            took = res_h * (rng.uniform(0.25, 0.95) if within else rng.uniform(1.05, 1.8))
            resolved = created + H(took)
            if resolved > E - H(2):
                resolved = E - H(rng.uniform(2, 30))
            auto = rng.random() < 0.15
            closed = resolved + (D(7) if auto else H(rng.uniform(2, 60)))
            if closed > E:
                continue
            reopened = rng.random() < 0.06
            sr = self.make_sr(category=cat, lat=lat, lon=lon, created=created, status="CLOSED", priority=pr,
                              closure_type="AUTO" if auto else "CITIZEN", resolved_at=resolved, closed_at=closed,
                              reopen_count=1 if reopened else 0, sla_state="STOPPED",
                              reporter_count=rng.choice([1, 1, 1, 2, 3]),
                              escalation_level=0 if within else rng.choice([1, 1, 2]))
            steps = [("SUBMITTED", created, "HUMAN"), ("ASSIGNED", created + H(rng.uniform(0.5, 6)), "HUMAN"),
                     ("IN_PROGRESS", created + H(took * 0.4), "SYSTEM"), ("WORK_COMPLETED", resolved - H(3), "SYSTEM"),
                     ("VERIFIED", resolved - H(1), "HUMAN"), ("RESOLVED", resolved, "SYSTEM"),
                     ("CLOSED", closed, "SYSTEM" if auto else "HUMAN")]
            self.history_rows(sr, steps)
            self.make_wo(sr, self.crew_for(ward), "VERIFIED", created + H(1), started_at=created + H(took * 0.4),
                         completed_at=resolved - H(3), verified_at=resolved - H(1), verified_by=self.users["control"].id,
                         audit_verdict="PASS", audit_score=rng.randint(78, 98))

    # ---------------------------------------------------------------- demo-specific state
    def repaired_spot(self) -> None:
        lat, lon = geo.POTHOLE_REPAIRED
        created = E - D(16)
        sr = self.make_sr(category="POTHOLE", lat=lat, lon=lon, created=created, status="CLOSED", priority="P2",
                          description="Pothole on Uttarahalli Main Road near the bus stop.", closure_type="CITIZEN",
                          resolved_at=E - D(9.5), closed_at=E - D(9), sla_state="STOPPED")
        self.history_rows(sr, [("SUBMITTED", created, "HUMAN"), ("ASSIGNED", created + H(3), "HUMAN"),
                               ("IN_PROGRESS", E - D(11), "SYSTEM"), ("WORK_COMPLETED", E - D(10.2), "SYSTEM"),
                               ("VERIFIED", E - D(10), "HUMAN"), ("RESOLVED", E - D(9.5), "SYSTEM"), ("CLOSED", E - D(9), "HUMAN")])
        self.make_wo(sr, "W15-A", "VERIFIED", created + H(4), scope="Patch pothole with hot-mix",
                     root_cause="Surface failure after BWSSB pipeline cutting", started_at=E - D(11),
                     completed_at=E - D(10.2), verified_at=E - D(10), verified_by=self.users["control"].id,
                     audit_verdict="PASS", audit_score=84)

    def streetlight_context(self) -> None:
        """Two open streetlight complaints near pole 00871 (different poles, same feeder)."""
        for (lat, lon), age_h, asset in [((12.9085, 77.4836), 50, "STREETLIGHT-W12-00870"),
                                         ((12.9071, 77.4818), 26, "STREETLIGHT-W12-00872")]:
            created = E - H(age_h)
            sr = self.make_sr(category="STREETLIGHT", lat=lat, lon=lon, created=created, status="ASSIGNED", priority="P3",
                              description="Streetlight not working near Kengeri bus stand; area dark after 7 pm.",
                              asset_id=asset)
            self.history_rows(sr, [("SUBMITTED", created, "HUMAN"), ("ASSIGNED", created + H(2), "HUMAN")])
            self.db.add(AssetEvent(asset_id=asset, type="COMPLAINT", date=created, note="Light not working", sr_id=sr.id))

    def atrisk_job(self) -> None:
        lat, lon = geo.ATRISK_JOB
        created = E - H(84)  # P2 pothole, 120 h SLA -> 70% at DEMO_EPOCH, AT_RISK 6 SLA-hours later
        sr = self.make_sr(category="POTHOLE", lat=lat, lon=lon, created=created, status="ASSIGNED", priority="P2",
                          description="Deep pothole on Kengeri Satellite Town 1st Main near the Ganesha temple; two-wheelers swerving into traffic.",
                          citizen=self.users["citizen3"], sla_state="ON_TRACK")
        self.history_rows(sr, [("SUBMITTED", created, "HUMAN"), ("ASSIGNED", created + H(3), "HUMAN")])
        self.make_wo(sr, "W12-B", "ASSIGNED", created + H(4), scope="Fill and compact pothole (approx. 1.2 m x 0.8 m)",
                     root_cause="Water stagnation weakened the surface", est_cost_inr=7500,
                     materials={"cold_mix_bitumen": 0.5})

    def open_backlog(self) -> None:
        """Open complaints: ones next to 'seeded_open' potholes, then fill crews to their target load."""
        for pid, kind, (lat, lon), _ in geo.TRUE_POTHOLES:
            if kind != "seeded_open":
                continue
            la, lo = jitter(lat, lon, 8)
            created = E - H(rng.uniform(20, 70))
            ward = geo.ward_of(la, lo)
            status = rng.choice(["ASSIGNED", "IN_PROGRESS"])
            sr = self.make_sr(category="POTHOLE", lat=la, lon=lo, created=created, status=status, priority="P3")
            steps = [("SUBMITTED", created, "HUMAN"), ("ASSIGNED", created + H(2), "HUMAN")]
            if status == "IN_PROGRESS":
                steps.append(("IN_PROGRESS", created + H(8), "SYSTEM"))
            self.history_rows(sr, steps)
            crew = self.crew_for(ward)
            if self.crew_load[crew] >= dict((c[0], c[6]) for c in CREWS)[crew]:
                crew = [c[0] for c in CREWS if c[1] == ward and c[6] > self.crew_load[c[0]]][0] if any(
                    c[1] == ward and c[6] > self.crew_load[c[0]] for c in CREWS) else crew
            self.make_wo(sr, crew, "IN_PROGRESS" if status == "IN_PROGRESS" else "ASSIGNED", created + H(3),
                         started_at=created + H(8) if status == "IN_PROGRESS" else None,
                         materials={"cold_mix_bitumen": 0.5})
        for cid, ward, skills, _cap, _base, _c, target in CREWS:
            while self.crew_load[cid] < target:
                cat = rng.choice([c for c in ("POTHOLE", "DRAIN_BLOCKED", "STREETLIGHT", "DAMAGED_ROAD")
                                  if {"POTHOLE": "ROADS", "DAMAGED_ROAD": "ROADS", "DRAIN_BLOCKED": "DRAINS",
                                      "STREETLIGHT": "ELECTRICAL"}[c] in skills])
                lat, lon = random_point_in(ward)
                created = E - H(rng.uniform(10, 60))
                sr = self.make_sr(category=cat, lat=lat, lon=lon, created=created, status="ASSIGNED", priority="P3")
                self.history_rows(sr, [("SUBMITTED", created, "HUMAN"), ("ASSIGNED", created + H(2), "HUMAN")])
                self.make_wo(sr, cid, "ASSIGNED", created + H(3))
        # a few fresh SUBMITTED complaints so every officer queue has something to triage
        for ward in ("W12", "W13", "W14", "W15"):
            for _ in range(2):
                cat = rng.choice(["GARBAGE", "WATER_LEAK", "DRAIN_BLOCKED", "STREETLIGHT"])
                lat, lon = random_point_in(ward)
                created = E - H(rng.uniform(0.5, 6))
                sr = self.make_sr(category=cat, lat=lat, lon=lon, created=created, status="SUBMITTED",
                                  priority=None, owner=True)
                self.history_rows(sr, [("SUBMITTED", created, "HUMAN")])


def analyse_submitted(db) -> None:
    """Seeded complaints awaiting acceptance get a System Analysis too (rule-based, so seeding never spends model quota)."""
    from app.agents.investigator import investigator
    from app.agents.runtime.loop import run_agent

    ids = list(db.scalars(text("SELECT id FROM service_requests WHERE status = 'SUBMITTED' ORDER BY id")))
    mode, settings.agent_mode = settings.agent_mode, "rules"
    try:
        for sr_id in ids:
            run_agent(investigator, "seed.backfill", {"id": sr_id})
    finally:
        settings.agent_mode = mode


DEMO_STEPS = """
=====================================================================
 CivicFlow demo is seeded.  Clock frozen-origin: {epoch}  TIME_SCALE={scale}
 Web: http://localhost:5173    API docs: http://localhost:8000/docs
---------------------------------------------------------------------
 Logins (OTP is shown on screen):
   citizen1 (Kannada) | citizen2 | citizen3
   officer.w12 | officer.w13 | officer.w14 | officer.w15 | zonal.west
   field.w12a | field.w12b | field.w13a | field.w13b | field.w14a | field.w15a
   control  (Executive Engineer / Commissioner)
---------------------------------------------------------------------
 1. citizen1 lodges a pothole near Govt. Higher Primary School, Kengeri (pin is preset)
 2. citizen2 and citizen3 report the same pothole -> auto-merged, reporter count 3
 3. make sim  -> vehicles confirm the school pothole, new Mysore Road complaint, speed breakers filtered
 4. citizen2 reports streetlight at Kengeri bus stand -> repeat failure, BESCOM referral
    (advance the clock; follow-ups, then L2 escalation; reply from the Agency Inbox)
 5. officer.w12 accepts the pothole brief -> work order -> field.w12a uploads far photo -> FAIL -> good photo -> PASS
    -> control approves -> citizen1 confirms with 5 stars
 6. Wait ~6 min (or advance 6 h): crew W12-B job hits 75% SLA -> reassignment to W13-B proposed -> officer approves
 7. make rain -> ~25 flood complaints -> 2 incidents, advisory -> control publishes -> ticker
 8. control: KPIs
=====================================================================
"""


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--reset", action="store_true")
    ap.add_argument("--demo", action="store_true")
    args = ap.parse_args()
    db = SessionLocal()
    try:
        if args.reset:
            reset(db)
        if db.scalar(text("SELECT count(*) FROM wards")):
            print("Already seeded (use --reset to rebuild).")
            return
        clock_state.reset(db, E)
        db.commit()
        clock.freeze(E)  # seed timestamps (default=now()) land exactly on the epoch
        Seeder(db).run()
        clock.load(clock.dump() | {"frozen": None})
        clock.configure(settings.time_scale, E)
        clock_state.save(db)
        db.commit()
        analyse_submitted(db)
        counts = {t: db.scalar(text(f'SELECT count(*) FROM "{t}"')) for t in
                  ("service_requests", "work_orders", "assets", "users", "sensitive_places", "status_events")}
        print("Seeded:", counts)
        if args.demo:
            print(DEMO_STEPS.format(epoch=E.isoformat(), scale=settings.time_scale))
    finally:
        db.close()


if __name__ == "__main__":
    main()
