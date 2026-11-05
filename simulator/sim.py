"""CivicFlow connected-vehicle simulator (SIMULATED OEM feed).

No real OEM data is public, so this script plays a partner that follows the
documented ingestion contract (docs/API.md, POST /api/v1/ingest/detections).
It sends only hazard points plus a rotating, salted vehicle reference: no VIN,
rider, phone or trip trace.

Coordinates come from the API (GET /api/v1/demo/points) so the simulator and the
seed always agree.

  python sim.py --once                 # one full pass, then ask Sensing to run now
  python sim.py --stream --rate 5      # keep sending ~5 detections/second (Ctrl+C to stop)
  python sim.py --scenario rain        # weather alert + ~25 flood/drain complaints
  python sim.py --clear-weather        # end the simulated weather alert

Standard library only.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import random
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timedelta, timezone

IST = timezone(timedelta(hours=5, minutes=30))
BATCH = 500  # API limit is 1000


# --------------------------------------------------------------------------- HTTP
class Api:
    def __init__(self, base: str, key: str):
        self.base = base.rstrip("/") + "/api/v1"
        self.key = key

    def _req(self, method: str, path: str, body: bytes | None = None, headers: dict | None = None):
        req = urllib.request.Request(self.base + path, data=body, method=method, headers=headers or {})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                raw = r.read()
                return json.loads(raw) if raw else None
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "replace")
            try:
                detail = json.loads(detail).get("detail", detail)
            except (ValueError, AttributeError):
                pass
            raise SystemExit(f"{method} {path} failed: HTTP {e.code}: {detail}") from None
        except urllib.error.URLError as e:
            raise SystemExit(f"Cannot reach the API at {self.base}: {e.reason}. Is it running?") from None

    def get(self, path: str):
        return self._req("GET", path)

    def post_json(self, path: str, payload, headers: dict | None = None):
        h = {"Content-Type": "application/json", **(headers or {})}
        return self._req("POST", path, json.dumps(payload).encode(), h)

    def post_form(self, path: str, fields: dict):
        body = urllib.parse.urlencode({k: v for k, v in fields.items() if v is not None}).encode()
        return self._req("POST", path, body, {"Content-Type": "application/x-www-form-urlencoded"})

    def ingest(self, records: list[dict]) -> dict:
        return self.post_json(
            "/ingest/detections",
            records,
            {"X-API-Key": self.key, "Idempotency-Key": str(uuid.uuid4())},
        )


# --------------------------------------------------------------------------- geometry
def jitter(lat: float, lon: float, metres: float, rng: random.Random) -> tuple[float, float]:
    """Random point within `metres` of (lat, lon), uniform over the disc."""
    r = metres * math.sqrt(rng.random())
    theta = rng.random() * 2 * math.pi
    dlat = (r * math.cos(theta)) / 111_320
    dlon = (r * math.sin(theta)) / (111_320 * math.cos(math.radians(lat)))
    return round(lat + dlat, 6), round(lon + dlon, 6)


# --------------------------------------------------------------------------- detections
class Feed:
    def __init__(self, points: dict, now: datetime, rng: random.Random):
        self.p = points
        self.now = now
        self.rng = rng
        self.run = uuid.uuid4().hex[:6]
        self.n = 0
        # Vehicle refs are salted hashes that rotate daily (privacy: counts distinct vehicles, not who).
        self.salt = f"civicflow-oem-sim-{now.date().isoformat()}"

    def vehicle(self, label: str) -> str:
        return hashlib.sha256(f"{self.salt}:{label}".encode()).hexdigest()[:16]

    def record(self, lat, lon, vehicle, hazard="POTHOLE", conf=0.85, jolt=1.8, speed=None, minutes_ago=None):
        self.n += 1
        ago = self.rng.uniform(5, 240) if minutes_ago is None else minutes_ago
        return {
            "source_record_id": f"oem-sim-{self.run}-{self.n:06d}",
            "lat": lat,
            "lon": lon,
            "hazard_type": hazard,
            "detected_at": (self.now - timedelta(minutes=ago)).isoformat(timespec="seconds"),
            "confidence": round(min(0.99, max(0.05, conf)), 2),
            "speed_kmph": speed if speed is not None else self.rng.randint(18, 45),
            "vertical_accel_peak_g": round(jolt, 2),
            "vehicle_ref": vehicle,
            "image_url": None,
        }

    def potholes(self) -> list[dict]:
        out = []
        for ph in self.p["potholes"]:
            weak = ph.get("kind") == "weak"
            for v in range(ph["vehicles"]):
                veh = self.vehicle(f"{ph['id']}-v{v}")
                for _hit in range(2):  # each vehicle hits it about twice
                    lat, lon = jitter(ph["lat"], ph["lon"], 6, self.rng)
                    conf = self.rng.gauss(0.6 if weak else 0.86, 0.04)
                    out.append(self.record(lat, lon, veh, "POTHOLE", conf, self.rng.uniform(1.4, 2.4)))
        return out

    def known_features(self) -> list[dict]:
        """Speed breakers and the rail crossing: many vehicles, big jolts. Sensing must filter these."""
        out = []
        feats = [("SB", f) for f in self.p.get("speed_breakers", [])] + [("RC", f) for f in self.p.get("rail_crossings", [])]
        for i, (kind, f) in enumerate(feats):
            for v in range(self.rng.randint(5, 6)):
                veh = self.vehicle(f"{kind}{i}-v{v}")
                lat, lon = jitter(f["lat"], f["lon"], 5, self.rng)
                out.append(self.record(lat, lon, veh, "ROUGH_SURFACE", self.rng.gauss(0.8, 0.05), self.rng.uniform(1.8, 2.8)))
        return out

    def noise(self, count: int = 25) -> list[dict]:
        """One-off single-vehicle bumps anywhere in the city (must not become complaints)."""
        b = self.p["bbox"]
        out = []
        for i in range(count):
            lat = round(self.rng.uniform(b["lat_min"] + 0.002, b["lat_max"] - 0.002), 6)
            lon = round(self.rng.uniform(b["lon_min"] + 0.002, b["lon_max"] - 0.002), 6)
            out.append(self.record(lat, lon, self.vehicle(f"noise-{self.run}-{i}"), "DAMAGED_ROAD",
                                   self.rng.uniform(0.35, 0.7), self.rng.uniform(1.0, 1.6)))
        return out

    def bad(self) -> list[dict]:
        """A few invalid records to show validation and the dead-letter table (Data Sources)."""
        b = self.p["bbox"]
        v = self.vehicle("bad")
        outside = self.record(13.2, 77.9, v)                               # outside the city boundary
        future = self.record(b["lat_min"] + 0.03, b["lon_min"] + 0.03, v, minutes_ago=-180)  # in the future
        old = self.record(b["lat_min"] + 0.03, b["lon_min"] + 0.03, v, minutes_ago=60 * 24 * 40)  # 40 days old
        pii = self.record(b["lat_min"] + 0.03, b["lon_min"] + 0.03, v)
        pii["vin"] = "MD2A11CZ0PCX00000"                                    # PII must be refused
        return [outside, future, old, pii]

    def full_pass(self, with_bad: bool) -> list[dict]:
        recs = self.potholes() + self.known_features() + self.noise()
        if with_bad:
            recs += self.bad()
        self.rng.shuffle(recs)
        return recs


# --------------------------------------------------------------------------- modes
def sim_now(api: Api) -> datetime:
    """Use the backend's simulated clock so timestamps are never 'in the future' for it."""
    try:
        return datetime.fromisoformat(api.get("/clock")["now"]).astimezone(IST)
    except (KeyError, TypeError, ValueError):
        return datetime.now(IST)


def send(api: Api, records: list[dict]) -> dict:
    total = {"received": 0, "accepted": 0, "rejected": 0, "duplicates": 0}
    reasons: dict[str, int] = {}
    for i in range(0, len(records), BATCH):
        res = api.ingest(records[i : i + BATCH]) or {}
        for k in total:
            total[k] += int(res.get(k, 0) or 0)
        for r in res.get("rejections", []):
            reasons[r.get("reason", "?")] = reasons.get(r.get("reason", "?"), 0) + 1
    total["rejection_reasons"] = reasons
    return total


def run_once(api: Api, rng: random.Random, with_bad: bool, sense: bool) -> None:
    points = api.get("/demo/points")
    feed = Feed(points, sim_now(api), rng)
    recs = feed.full_pass(with_bad)
    print(f"Sending {len(recs)} detections (simulated OEM feed) ...")
    res = send(api, recs)
    print(f"  accepted {res['accepted']}, rejected {res['rejected']}, duplicates {res['duplicates']}")
    for reason, n in res["rejection_reasons"].items():
        print(f"    rejected x{n}: {reason}")
    if sense:
        try:
            out = api.post_json("/demo/run/sensing", {})
            print(f"Road Hazard Sensing run started (run {out.get('run_id') if out else '?'}). See Control Room > Road Hazard Map.")
        except SystemExit as e:
            print(f"  (could not trigger Sensing now: {e}; it runs on its own schedule)")


def run_stream(api: Api, rng: random.Random, rate: float, duration: float | None) -> None:
    points = api.get("/demo/points")
    started = time.monotonic()
    sent = accepted = 0
    print(f"Streaming about {rate:g} detections/second. Ctrl+C to stop.")
    try:
        while duration is None or time.monotonic() - started < duration:
            feed = Feed(points, sim_now(api), rng)
            pool = feed.full_pass(with_bad=False)
            for i in range(0, len(pool), max(1, int(rate))):
                if duration is not None and time.monotonic() - started >= duration:
                    break
                chunk = pool[i : i + max(1, int(rate))]
                for r in chunk:  # stream = "just now"
                    r["detected_at"] = (feed.now - timedelta(seconds=rng.uniform(0, 30))).isoformat(timespec="seconds")
                res = send(api, chunk)
                sent += len(chunk)
                accepted += res["accepted"]
                print(f"\r  sent {sent}, accepted {accepted}", end="", flush=True)
                time.sleep(1.0)
    except KeyboardInterrupt:
        pass
    print(f"\nStopped. Sent {sent}, accepted {accepted}.")


RAIN_TEXT = {
    "WATERLOGGING": [
        "Knee-deep water under the underpass, two-wheelers stuck.",
        "Road completely flooded after the rain, buses not able to pass.",
        "Water entering shops near the underpass, drain overflowing.",
        "Heavy waterlogging on the service road, cars stalled.",
        "Underpass flooded, please send pump urgently.",
    ],
    "DRAIN_BLOCKED": [
        "Storm water drain blocked with garbage, water overflowing on road.",
        "Drain choked near the arch, sewage mixing with rain water.",
        "Open drain overflowing into houses after heavy rain.",
        "Culvert blocked, water not draining from main road.",
    ],
}


def run_rain(api: Api, rng: random.Random, surge_now: bool) -> None:
    points = api.get("/demo/points")
    areas = points["rain_areas"]
    print("Raising simulated weather alert: Heavy rain warning ...")
    api.post_json("/demo/weather-alert", {
        "title": "Heavy rain warning (Simulated)", "severity": "ORANGE",
        "area_name": "Kengeri / RR Nagar", "hours": 6,
    })
    plan = []
    for idx, area in enumerate(areas):
        cat = "WATERLOGGING" if idx == 0 else "DRAIN_BLOCKED"
        plan += [(area, cat)] * int(area.get("reports", 10))
    rng.shuffle(plan)
    print(f"Filing {len(plan)} citizen complaints around {', '.join(a['name'] for a in areas)} ...")
    made = []
    for i, (area, cat) in enumerate(plan):
        lat, lon = jitter(area["lat"], area["lon"], 400, rng)
        ack = api.post_form("/complaints", {
            "category": cat,
            "description": f"{rng.choice(RAIN_TEXT[cat])} (near {area['name']})",
            "lat": f"{lat:.6f}", "lon": f"{lon:.6f}",
            "landmark": area["name"],
            "contact_name": f"Rain reporter {i + 1}",
            "contact_phone": f"98{rng.randint(10_000_000, 99_999_999)}",
            "anonymous": "false", "language": rng.choice(["en", "en", "kn"]),
        })
        made.append(ack["grievance_no"])
        print(f"\r  filed {len(made)}/{len(plan)}", end="", flush=True)
        time.sleep(0.15)
    print(f"\nFiled {len(made)} complaints ({made[0]} ... {made[-1]}).")
    if surge_now:
        try:
            api.post_json("/demo/run/surge", {})
            print("Surge Commander run started. See Control Room > Incidents.")
        except SystemExit as e:
            print(f"  (could not trigger Surge now: {e}; it checks every 20 s)")


# --------------------------------------------------------------------------- main
def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="CivicFlow simulated connected-vehicle feed and rain scenario.")
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--once", action="store_true", help="send one full pass of detections")
    mode.add_argument("--stream", action="store_true", help="send detections continuously")
    mode.add_argument("--scenario", choices=["rain"], help="run a scripted scenario")
    mode.add_argument("--clear-weather", action="store_true", help="end the simulated weather alert")
    ap.add_argument("--rate", type=float, default=5, help="detections per second for --stream (default 5)")
    ap.add_argument("--duration", type=float, default=None, help="seconds to stream (default: until Ctrl+C)")
    ap.add_argument("--no-bad", action="store_true", help="--once: skip the 4 deliberately invalid records")
    ap.add_argument("--no-trigger", action="store_true", help="do not ask the backend to run the agent immediately")
    ap.add_argument("--seed", type=int, default=None, help="random seed for repeatable runs")
    ap.add_argument("--api", default=os.environ.get("CIVICFLOW_API", "http://localhost:8000"),
                    help="API base URL (env CIVICFLOW_API; default http://localhost:8000)")
    ap.add_argument("--key", default=os.environ.get("OEM_SIM_API_KEY", "oem-sim-demo-key"),
                    help="ingestion X-API-Key (env OEM_SIM_API_KEY)")
    args = ap.parse_args(argv)

    api = Api(args.api, args.key)
    rng = random.Random(args.seed)
    if args.once:
        run_once(api, rng, with_bad=not args.no_bad, sense=not args.no_trigger)
    elif args.stream:
        run_stream(api, rng, args.rate, args.duration)
    elif args.scenario == "rain":
        run_rain(api, rng, surge_now=not args.no_trigger)
    elif args.clear_weather:
        api.post_json("/demo/weather-alert/clear", {})
        print("Simulated weather alert cleared.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
