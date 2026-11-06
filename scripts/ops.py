"""Operator commands for running the story on cue (standard library only).

    python scripts/ops.py clock              # show the SLA clock
    python scripts/ops.py pause              # stop the SLA clock (after a reset, until you go on stage)
    python scripts/ops.py resume             # start it again
    python scripts/ops.py advance 6          # move the SLA clock forward 6 hours, then run the SLA check
    python scripts/ops.py run followup       # SLA check + agency follow-ups now
    python scripts/ops.py run sensing        # Road Hazard Sensing now
    python scripts/ops.py run surge          # Surge Commander now

Needs DEMO_MODE=true on the API (the default). --api or $CIVICFLOW_API for another address.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.request


def call(base: str, method: str, path: str, body: dict | None = None) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(base + path, data=data, method=method, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read() or b"{}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--api", default=os.environ.get("CIVICFLOW_API", "http://localhost:8000"))
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("clock")
    sub.add_parser("pause")
    sub.add_parser("resume")
    adv = sub.add_parser("advance")
    adv.add_argument("hours", type=float)
    run = sub.add_parser("run")
    run.add_argument("agent", choices=["followup", "sensing", "surge"])
    a = ap.parse_args()
    base = a.api.rstrip("/") + "/api/v1"
    if a.cmd == "clock":
        c = call(base, "GET", "/clock")
        print(f"SLA clock: {c['now']}  (x{c['scale']:g}){'  PAUSED' if c.get('frozen') else ''}")
    elif a.cmd in ("pause", "resume"):
        c = call(base, "POST", f"/demo/clock/{a.cmd}", {})
        print(f"SLA clock {'paused' if c.get('frozen') else 'running'} at {c['now']}")
    elif a.cmd == "advance":
        c = call(base, "POST", "/demo/clock/advance", {"hours": a.hours})
        print(f"SLA clock moved forward {a.hours:g} h -> {c['now']}")
        time.sleep(6)  # the API picks up the new clock within 5 s
        call(base, "POST", "/demo/run/followup", {})
        print("SLA check and follow-ups started. Watch the Agent Activity Log.")
    else:
        call(base, "POST", f"/demo/run/{a.agent}", {})
        print(f"{a.agent} started. Watch the Agent Activity Log.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
