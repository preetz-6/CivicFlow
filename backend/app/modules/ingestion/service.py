"""Road-hazard detection ingestion: validate & normalise -> raw_detections, failures -> rejected_detections.

Never silently drops a record. Never stores personal data: payloads carrying VIN, rider name, phone or
trip traces are rejected outright (and the offending fields are not kept in the dead-letter copy).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from shapely.geometry import Point
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.bus import bus
from app.core.clock import IST, now
from app.models import DataSource, RawDetection, RejectedDetection
from app.modules import geo
from app.seed.geo import CITY_BOUNDARY

MAX_BATCH = 1000
MAX_AGE = timedelta(days=30)
FORBIDDEN_KEYS = {"vin", "rider_name", "rider", "name", "phone", "mobile", "email", "trip", "trip_id", "route",
                  "trace", "trip_trace", "track", "driver", "driver_name", "licence", "license_plate", "plate"}
HAZARD_MAP = {
    "POTHOLE": "POTHOLE", "POT_HOLE": "POTHOLE", "PIT": "POTHOLE",
    "DAMAGED_ROAD": "DAMAGED_ROAD", "DAMAGE": "DAMAGED_ROAD", "BROKEN_ROAD": "DAMAGED_ROAD",
    "ROUGH_SURFACE": "ROUGH_SURFACE", "ROUGH": "ROUGH_SURFACE", "BUMPY": "ROUGH_SURFACE",
}


class Reject(Exception):
    pass


def _f(v, name, lo=None, hi=None, required=True):
    if v is None or v == "":
        if required:
            raise Reject(f"missing {name}")
        return None
    try:
        x = float(v)
    except (TypeError, ValueError):
        raise Reject(f"{name} is not a number") from None
    if (lo is not None and x < lo) or (hi is not None and x > hi):
        raise Reject(f"{name} {x} out of range")
    return x


def _ts(v) -> datetime:
    if not v:
        raise Reject("missing detected_at")
    try:
        t = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    except ValueError:
        raise Reject("detected_at is not ISO-8601") from None
    if t.tzinfo is None:
        t = t.replace(tzinfo=IST)
    return t.astimezone(timezone.utc)


def normalise(rec: dict) -> dict:
    if not isinstance(rec, dict):
        raise Reject("record is not an object")
    bad = sorted(k for k in rec if k.lower() in FORBIDDEN_KEYS)
    if bad:
        raise Reject(f"personal data not accepted: {', '.join(bad)}")
    rid = str(rec.get("source_record_id") or "").strip()
    if not rid or len(rid) > 64:
        raise Reject("missing or too long source_record_id")
    lat = _f(rec.get("lat"), "lat", -90, 90)
    lon = _f(rec.get("lon"), "lon", -180, 180)
    if not CITY_BOUNDARY.covers(Point(lon, lat)):
        raise Reject("outside city boundary")
    t = _ts(rec.get("detected_at"))
    n = now()
    if t > n + timedelta(minutes=5):
        raise Reject("detected_at is in the future")
    if t < n - MAX_AGE:
        raise Reject("detected_at older than 30 days")
    conf = rec.get("confidence")
    conf = 0.5 if conf is None or conf == "" else _f(conf, "confidence", 0, 1)
    ht = str(rec.get("hazard_type") or "").strip().upper().replace(" ", "_").replace("-", "_")
    if ht not in HAZARD_MAP:
        raise Reject(f"unknown hazard_type '{rec.get('hazard_type')}'")
    vref = str(rec.get("vehicle_ref") or "").strip()
    if not vref or len(vref) > 64:
        raise Reject("missing vehicle_ref (rotating hashed reference)")
    return {
        "source_record_id": rid, "lat": lat, "lon": lon, "detected_at": t, "confidence": conf,
        "hazard_type": HAZARD_MAP[ht], "speed_kmph": _f(rec.get("speed_kmph"), "speed_kmph", 0, 200, required=False),
        "vertical_accel_peak_g": _f(rec.get("vertical_accel_peak_g"), "vertical_accel_peak_g", 0, 20, required=False),
        "vehicle_ref": vref, "image_url": rec.get("image_url") or None,
    }


def _scrub(rec) -> dict | None:
    if not isinstance(rec, dict):
        return {"raw": str(rec)[:500]}
    return {k: v for k, v in rec.items() if k.lower() not in FORBIDDEN_KEYS}


def ingest(db: Session, source: DataSource, records: list) -> dict:
    accepted = dup = 0
    rejections = []
    seen: set[str] = set()
    for i, rec in enumerate(records):
        rid = rec.get("source_record_id") if isinstance(rec, dict) else None
        try:
            n = normalise(rec)
            if n["source_record_id"] in seen or db.scalar(select(RawDetection.id).where(
                    RawDetection.source_id == source.id, RawDetection.source_record_id == n["source_record_id"])):
                dup += 1
                raise Reject("duplicate source_record_id (already ingested)")
            seen.add(n["source_record_id"])
            db.add(RawDetection(source_id=source.id, location=geo.make_point(n["lat"], n["lon"]),
                                raw_payload=_scrub(rec), ingested_at=now(),
                                **{k: v for k, v in n.items() if k not in ("lat", "lon")}))
            accepted += 1
        except Reject as e:
            db.add(RejectedDetection(source_id=source.id, source_record_id=str(rid)[:64] if rid else None,
                                     reason=str(e)[:160], raw_payload=_scrub(rec), at=now()))
            rejections.append({"index": i, "source_record_id": rid, "reason": str(e)})
    source.accepted_count = (source.accepted_count or 0) + accepted
    source.rejected_count = (source.rejected_count or 0) + len(rejections)
    source.last_ingested_at = now()
    db.flush()
    if accepted:
        bus.publish(db, "detections.ingested", {"source": source.id, "accepted": accepted})
    return {"received": len(records), "accepted": accepted, "rejected": len(rejections), "duplicates": dup,
            "rejections": rejections[:100]}
