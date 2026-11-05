# CivicFlow API

The full, always-current reference is the OpenAPI page served by the backend: **http://localhost:8000/docs** (raw schema at `/openapi.json`). The web app's types are generated from it (`cd web && npm run gen:api`).

Base path: `/api/v1`. Staff and citizen logins use a cookie session; send requests with credentials. Errors are always `{"detail": "..."}` with 400 / 401 / 403 / 404 / 409 / 422.

## Main groups

| Group | Endpoints |
|---|---|
| Auth (demo OTP) | `GET /auth/demo-users` · `POST /auth/login {username}` → `{sent_to, otp_demo}` · `POST /auth/verify {username, otp}` (sets the cookie) · `GET /auth/me` · `POST /auth/logout` |
| Citizen | `POST /complaints` (multipart: category, description, lat, lon, landmark, address, contact_name, contact_phone, anonymous, language, photo) → acknowledgement slip · `GET /complaints/track?no=&code=` (code = tracking code or mobile) · `POST /complaints/{id}/confirm {code, rating, comment}` · `POST /complaints/{id}/reopen {code, reason}` |
| Officer | `GET /officer/queue` (ward-scoped; Control Room sees all) · `GET /officer/stats` · `GET /complaints/{id}` (detail with `analysis` and `allowed_actions`) · `POST /complaints/{id}/accept`, `/override`, `/hold`, `/resume`, `/reject`, `/merge/{parent}`, `/unmerge` · `GET /crews` · `POST /complaints/{id}/work-orders` · `GET /reassignments?status=PENDING` · `POST /reassignments/{id}/approve`, `/reject` |
| Field team | `GET /field/jobs` · `GET /field/jobs/{id}` · `POST /field/jobs/{id}/start`, `/resume`, `/photos` (multipart kind, photo), `/complete` |
| Control Room | `GET /control/verification` · `POST /work-orders/{id}/approve`, `/reject` · `GET /escalations` · `GET /hazards/map` · `GET /hazards/clusters` · `POST /hazards/clusters/{id}/confirm`, `/dismiss` · `GET /data-sources` · `GET /incidents` · `POST /incidents/{id}/publish`, `/close` · `GET /weather/alerts` |
| Agent Activity Log | `GET /agent-runs` · `GET /agent-runs/{id}` (rationale, every step, input, output) · `POST /agent-runs/{id}/override` · `GET /agent-stats` |
| Public | `GET /public/stats` · `/public/ticker` · `/public/categories` · `/public/wards` · `/public/departments` · `/public/sla-policies` · `POST /public/visit` |
| Simulated agency | `GET /agency/inbox` · `POST /agency/referrals/{id}/reply {status, message}` |
| Demo only (`DEMO_MODE=true`) | `GET /clock` · `POST /demo/clock/advance {hours}` · `POST /demo/run/{sensing,surge,followup}` · `POST /demo/weather-alert`, `/demo/weather-alert/clear` · `GET /demo/points` · `GET /demo/photos/{variant}.jpg?wo_id=` |

## Ingestion contract (connected-vehicle hazard detections)

This is the contract a vehicle maker (OEM) would integrate with. In this prototype the partner is **simulated** by `simulator/sim.py`.

```
POST /api/v1/ingest/detections
X-API-Key: <per data source>            (demo: oem-sim-demo-key)
Idempotency-Key: <uuid>                 optional; a repeated key returns the first response
Content-Type: application/json

[ { "source_record_id": "oem-sim-000123",
    "lat": 12.9081, "lon": 77.4874,
    "hazard_type": "POTHOLE",            // POTHOLE | DAMAGED_ROAD | ROUGH_SURFACE
    "detected_at": "2026-11-05T09:12:44+05:30",
    "confidence": 0.82,                  // 0..1, default 0.5
    "speed_kmph": 32,
    "vertical_accel_peak_g": 1.9,
    "vehicle_ref": "salted-hash-rotated-daily",
    "image_url": null } ]
```

- A bare array or `{"records": [...]}`, at most **1000** records per request. `POST /api/v1/ingest/detections/csv` takes the same columns as a CSV upload.
- Response: `{received, accepted, rejected, duplicates, rejections: [{index, source_record_id, reason}]}`.
- **Validation:** inside the city boundary; `detected_at` not in the future and not older than 30 days; confidence 0–1; hazard type mapped to the internal enum; de-duplicated on (source, `source_record_id`). The original payload is kept as `raw_payload`.
- **Never silently dropped:** every failed record goes to `rejected_detections` with its reason (shown in Control Room → Road Hazard Map → Data Sources).
- **Privacy:** only hazard points and a rotating hashed vehicle reference (used to count distinct vehicles) are accepted. Records containing a VIN, rider name, phone number or trip trace are refused, and those fields are stripped even from the dead letter.
