# CivicFlow simulator (Simulated OEM feed)

No vehicle maker publishes its data, so this script plays a connected-vehicle partner
that follows the documented ingestion contract (`POST /api/v1/ingest/detections`,
`X-API-Key`, `Idempotency-Key`, at most 1000 records per batch). It sends only hazard
points and a daily-rotating salted vehicle reference: no VIN, rider, phone or trip trace.

Coordinates come from `GET /api/v1/demo/points`, so they always match the seed.

| Command | What it does |
|---|---|
| `python sim.py --once` | One pass: about 15 potholes hit by several vehicles each (GPS noise up to 6 m), 5 speed breakers and a rail crossing (must be filtered), single-vehicle noise, and 4 invalid records (outside the city, future, 40 days old, contains a VIN) that land in the dead letter. Then asks Road Hazard Sensing to run now. |
| `python sim.py --stream --rate 5` | Keeps sending about 5 detections per second until Ctrl+C (`--duration 60` to stop on its own). |
| `python sim.py --scenario rain` | Raises a simulated heavy-rain alert and files about 25 flood / blocked-drain complaints around the two rain areas, then asks the Surge Commander to run now. |
| `python sim.py --clear-weather` | Ends the simulated weather alert. |

Options: `--api` (default `$CIVICFLOW_API` or `http://localhost:8000`), `--key`
(default `$OEM_SIM_API_KEY` or `oem-sim-demo-key`), `--seed N` for a repeatable run,
`--no-bad`, `--no-trigger`.

Run with Docker (uses `http://api:8000` inside the compose network):

    docker compose run --rm simulator python sim.py --once
    docker compose run --rm simulator python sim.py --scenario rain

Or directly with Python 3.11+ (standard library only):

    python simulator/sim.py --once --api http://localhost:8000
