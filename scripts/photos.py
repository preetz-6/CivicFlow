"""Make completion photos for a work order, ready to upload from the Field Team screen.

    python scripts/photos.py                     # newest open job of field.w12a
    python scripts/photos.py WO-2026-001232      # a specific work order
    python scripts/photos.py --user field.w13b --password Field@2026

Writes into photos/<work order>/ (gitignored):
    1_after_at_site.jpg            correct: taken now, at the complaint site      -> PASS
    2_after_2km_away.jpg           GPS 2.1 km from the site                       -> FAIL, sent for rework
    3_after_before_assignment.jpg  taken two days before the job was assigned     -> FAIL
    4_after_no_location.jpg        no GPS / time inside the file                  -> needs a human (FLAG)
    5_after_reused.jpg             a copy of another job's photo                  -> FAIL
    0_before.jpg                   a before-photo at the site

Photos are stamped with the server's current time, so run this AFTER the job is assigned and just before
uploading. If real photos are placed in backend/app/seed/fixtures/ (pothole_before.jpg, pothole_after.jpg,
pothole_far.jpg), they are used instead of drawn ones. Standard library only.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from http.cookiejar import CookieJar
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FILES = [
    ("after_good", "1_after_at_site.jpg"),
    ("after_far", "2_after_2km_away.jpg"),
    ("after_old", "3_after_before_assignment.jpg"),
    ("after_noexif", "4_after_no_location.jpg"),
    ("after_reused", "5_after_reused.jpg"),
    ("before", "0_before.jpg"),
]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("wo", nargs="?", help="work order id (default: newest open job of --user)")
    ap.add_argument("--api", default=os.environ.get("CIVICFLOW_API", "http://localhost:8000"))
    ap.add_argument("--user", default="field.w12a")
    ap.add_argument("--password", default="Field@2026")
    ap.add_argument("--out", default=str(ROOT / "photos"))
    a = ap.parse_args()
    base = a.api.rstrip("/") + "/api/v1"
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(CookieJar()))

    wo = a.wo
    if not wo:
        req = urllib.request.Request(base + "/auth/login", data=json.dumps({"username": a.user, "password": a.password}).encode(),
                                     headers={"Content-Type": "application/json"}, method="POST")
        try:
            opener.open(req, timeout=20).read()
            jobs = json.loads(opener.open(base + "/field/jobs", timeout=20).read())
        except urllib.error.HTTPError as e:
            print(f"Could not log in as {a.user}: HTTP {e.code}", file=sys.stderr)
            return 1
        open_jobs = [j for j in jobs if j["status"] in ("IN_PROGRESS", "ASSIGNED", "REWORK")]
        if not open_jobs:
            print(f"{a.user} has no open jobs. Pass a work order id.", file=sys.stderr)
            return 1
        wo = max(open_jobs, key=lambda j: j["assigned_at"])["id"]

    out = Path(a.out) / wo
    out.mkdir(parents=True, exist_ok=True)
    for variant, name in FILES:
        try:
            data = opener.open(f"{base}/demo/photos/{variant}.jpg?wo_id={wo}", timeout=30).read()
        except urllib.error.HTTPError as e:
            print(f"{variant}: HTTP {e.code} (is the work order id right, and DEMO_MODE on?)", file=sys.stderr)
            return 1
        (out / name).write_bytes(data)
    print(f"Photos for {wo} written to {out}")
    for _, name in FILES:
        print("  ", name)
    print("Upload one with 'Upload after photo' on the job, then 'Mark completed'.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
