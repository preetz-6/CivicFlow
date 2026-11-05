"""Record the model's answers for the demo story, so the live demo can run with AGENT_MODE=replay.

Prereqs: stack running; in .env set AGENT_MODE=record (and LLM_MIN_INTERVAL_S=13 on a free tier), then
`docker compose up -d --force-recreate api` and reseed (`docker compose exec api python -m app.seed.build --reset`).
Run from the repo root with the backend venv (needs httpx):

    backend/.venv/Scripts/python scripts/record_demo.py        (Windows)
    backend/.venv/bin/python scripts/record_demo.py            (macOS/Linux)

It drives the same steps as docs/DEMO_SCRIPT.md through the real API, waiting for each agent run to finish.
Recordings land in backend/agent_cache/<agent>/. Commit them. Then set AGENT_MODE=replay for the demo.
"""
from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.seed import demo_story as S  # noqa: E402

B = "http://localhost:8000/api/v1"
pub = httpx.Client(base_url=B, timeout=120)


def login(user: str) -> httpx.Client:
    c = httpx.Client(base_url=B, timeout=120)
    otp = c.post("/auth/login", json={"username": user}).json()["otp_demo"]
    c.post("/auth/verify", json={"username": user, "otp": otp}).raise_for_status()
    return c


ctl = None


def wait_runs(agent: str | None = None, subject: str | None = None, at_least: int = 1, timeout: int = 900) -> list[dict]:
    """Wait until the given agent's runs (optionally for one subject) are finished."""
    t0 = time.time()
    while time.time() - t0 < timeout:
        params = {"page_size": 50}
        if agent:
            params["agent"] = agent
        if subject:
            params["subject_id"] = subject
        items = ctl.get("/agent-runs", params=params).json()["items"]
        done = [r for r in items if r["status"] != "RUNNING"]
        if len(done) >= at_least and not any(r["status"] == "RUNNING" for r in items):
            return done
        time.sleep(4)
    raise SystemExit(f"timed out waiting for {agent} {subject}")


def all_idle(timeout: int = 1200) -> None:
    t0 = time.time()
    while time.time() - t0 < timeout:
        items = ctl.get("/agent-runs", params={"page_size": 50}).json()["items"]
        if not any(r["status"] == "RUNNING" for r in items):
            return
        time.sleep(5)


def say(msg: str) -> None:
    print(time.strftime("%H:%M:%S"), msg, flush=True)


def show(run: dict) -> None:
    say(f"   -> {run['agent_label']}: {run['status']} model={run['model']} | {run['decision']}")


def lodge(cat: str, desc: str, phone: str, lat: float, lon: float) -> str:
    r = pub.post("/complaints", data={"category": cat, "description": desc, "lat": lat, "lon": lon, "contact_phone": phone})
    r.raise_for_status()
    return r.json()["grievance_no"]


def sim(*args: str) -> None:
    subprocess.run([sys.executable, str(ROOT / "simulator" / "sim.py"), *args, "--api", "http://localhost:8000"], check=True)


def photo(fld: httpx.Client, wo: str, variant: str) -> None:
    img = pub.get(f"/demo/photos/{variant}.jpg", params={"wo_id": wo}).content
    fld.post(f"/field/jobs/{wo}/photos", data={"kind": "AFTER"}, files={"photo": (f"{variant}.jpg", img, "image/jpeg")}).raise_for_status()
    fld.post(f"/field/jobs/{wo}/complete").raise_for_status()


def main() -> None:
    global ctl
    health = pub.get("/health").json()
    if health["agent_mode"] != "record":
        raise SystemExit(f"AGENT_MODE is {health['agent_mode']!r}; set AGENT_MODE=record in .env and recreate the api container")
    say(f"Recording with {health['llm_provider']} / {health['llm_model']}")
    ctl, off, fld = login("control"), login("officer.w12"), login("field.w12a")

    say("Step 1-2: school pothole x3")
    ids = []
    for desc, phone, dlat in S.POTHOLE_REPORTS:
        ids.append(lodge("POTHOLE", desc, phone, S.SCHOOL_PIN[0] + dlat, S.SCHOOL_PIN[1]))
        show(wait_runs("investigator", ids[-1])[0])
    school = ids[0]

    say("Step 3: simulator feed -> Road Hazard Sensing")
    sim("--once", "--seed", str(S.SIM_ONCE_SEED))
    show(wait_runs("sensing")[0])
    all_idle()

    say("Step 4: streetlight -> BESCOM referral -> follow-ups -> L2")
    sl = lodge("STREETLIGHT", S.STREETLIGHT_REPORT[0], S.STREETLIGHT_REPORT[1], *S.STREETLIGHT_PIN)
    show(wait_runs("investigator", sl)[0])
    off.post(f"/complaints/{sl}/accept", json={}).raise_for_status()

    say("Step 5: pothole work order -> far photo (FAIL) -> good photo (PASS) -> approve -> confirm")
    off.post(f"/complaints/{school}/accept", json={}).raise_for_status()
    wo = off.post(f"/complaints/{school}/work-orders", data={"crew_id": "W12-A", "scope": "Fill and compact pothole at school gate"}).json()["id"]
    fld.post(f"/field/jobs/{wo}/start").raise_for_status()
    photo(fld, wo, "after_far")
    show(wait_runs("auditor", wo)[0])
    time.sleep(31)  # 30 SLA-minutes on the 60x clock
    fld.post(f"/field/jobs/{wo}/start").raise_for_status()
    photo(fld, wo, "after_good")
    show(wait_runs("auditor", wo, at_least=2)[0])
    ctl.post(f"/work-orders/{wo}/approve").raise_for_status()
    time.sleep(4)  # VERIFIED -> RESOLVED happens in the background
    pub.post(f"/complaints/{school}/confirm", json={"code": S.POTHOLE_REPORTS[0][1], "rating": 5}).raise_for_status()

    say("Step 6 + 4b: clock +6 h (at-risk job), then 2 x 24 h (BESCOM follow-ups)")
    for h in (6.2, 24.2, 24.2):
        pub.post("/demo/clock/advance", json={"hours": h}).raise_for_status()
        time.sleep(7)  # clock sync
        pub.post("/demo/run/followup").raise_for_status()
        time.sleep(3)
        all_idle()
    for r in ctl.get("/agent-runs", params={"agent": "followup", "page_size": 10}).json()["items"][:4]:
        show(r)

    say("Step 7: rain scenario -> Surge Commander")
    sim("--scenario", "rain", "--seed", str(S.SIM_RAIN_SEED))
    all_idle()
    show(wait_runs("surge")[0])

    n = sum(1 for _ in (ROOT / "backend" / "agent_cache").rglob("*.json"))
    say(f"Done. {n} recorded model turns in backend/agent_cache/. Commit them, then set AGENT_MODE=replay.")


if __name__ == "__main__":
    main()
