# CivicFlow: Build Brief for Claude Code (24-hour hackathon)

> Original brief, kept verbatim as the specification. Team reality: **2 people, 2 Claude machines**. See `docs/BUILD_PLAN.md` §9 for how the work is split and §12 for the agreed cuts. Where BUILD_PLAN differs from this brief (e.g. Agent 2 runs on state changes, per-turn replay keys), BUILD_PLAN wins.

---

## 0. How to work with me

1. **Don't write code yet.** First do **Step 0: Build Plan** (Section 13). Explain the plan to me in plain language, then **stop and wait for my approval**.
2. After approval, build in the **checkpoints** in Section 12. At each checkpoint: run the tests, tell me what now works and how to see it, update `PROGRESS.md`, and wait for "continue".
3. We have **24 hours** and a team of 3–4 people. Pick **working and demoable** over feature-complete every time. If something is running late, cut from "Stretch" and never from the demo path.
4. **The agents need proper work. Everything else stays simple** (simple, not broken). Section 2 says exactly which is which.
5. Everything external is **simulated** behind a small adapter class: vehicle OEM feed, SMS/WhatsApp, weather, the external agencies (BESCOM/BWSSB). Label simulated parts in the UI and README.
6. One command runs everything: `docker compose up`. Also provide `make seed`, `make demo`, `make test`.
7. The app must work **without an LLM API key**. Every agent has a rule-based fallback, and there is a record/replay cache for the demo (Section 5.1).
8. Secrets go in `.env`; provide `.env.example`. Never hard-code keys.
9. Ask me before adding a major dependency that isn't listed here.

---

## 1. The problem

**Problem statement:** An Agentic Civic Operations System for Smart Cities (ID: DL-SJBIT-HK26-SSF009).

City corporations receive thousands of citizen complaints (potholes, garbage, broken streetlights, water leaks, blocked drains) through many channels. Three things go wrong:
1. **Routing is manual and slow:** nobody quickly works out which department, ward or agency owns the issue.
2. **Follow-up is poor:** cases sit idle, other agencies don't respond, nobody chases.
3. **Citizens are kept in the dark:** they never learn what happened, or why it's delayed.

**CivicFlow** is a multi-agent system. Autonomous AI agents investigate, route, chase, verify and coordinate civic issues from report to verified closure. Humans approve the decisions that affect a citizen's case.

**What the citizen sees:** Report issue → get acknowledgement → track progress → get resolution proof (before/after photo) → confirm or reopen → closed.

**Product name:** CivicFlow. **Fictional city body:** "CivicFlow Municipal Corporation", with Bengaluru as the demo geography (Kengeri / Rajarajeshwari Nagar area, near SJBIT).

---

## 2. What gets proper work and what stays simple

### Proper work (this is what we're judged on)
- The **5 agents** (Section 5) and the **shared agent framework** they run on.
- The **Agent Activity Log** that shows each agent's reasoning, the tools it called, and whether a human overrode it.
- The **Road Hazard data collection layer** (ingestion API, simulator, clustering).
- **Seed data**: the agents are only as smart as the data they can look up, so it must be realistic and connected.
- **Demo-path UI polish**: the screens in the demo story (Section 11).

### Simple but correct (the agents depend on these, so no bugs)
- Status flow: a small transition table that blocks invalid moves (Section 6).
- Data model (Section 7).
- Event bus: every status change publishes an event agents can subscribe to.
- Append-only audit log and agent decision log.

### Minimal (basic CRUD screens are fine)
- Login with seeded demo users (no real OTP; show the "OTP" on screen in demo mode).
- Officer queue: one filterable table plus the agent brief with Accept / Override.
- Field team screen: a list of my jobs, a photo upload, a status button.
- Notifications: an on-screen outbox table, no real SMS.
- Configuration: in seed/config files, **no admin UI**.

### Out of scope (mention as "future" in the README only)
Offline PWA, real WhatsApp/IVR, a public transparency dashboard, ERP/finance and invoices, a separate contractor portal, multi-city support, a separate inspection stage (merged into the work order), and any roles beyond the four in Section 8.

---

## 3. Tech stack

| Layer | Choice |
|---|---|
| Backend | Python 3.11+, **FastAPI**, SQLAlchemy 2.x, Alembic, Pydantic v2. One **modular monolith** (a package per module), no microservices |
| DB | **PostgreSQL 16 + PostGIS** (ward polygons, radius queries, `ST_ClusterDBSCAN`) |
| Events | In-process async publish/subscribe, with events persisted to an `events` table |
| Scheduler | APScheduler (Follow-up agent tick, Sensing agent clustering run, auto-close) |
| LLM | Anthropic Claude via the official `anthropic` SDK using **tool use**. Model from env `CIVICFLOW_LLM_MODEL` (default `claude-sonnet-5-5`), key from `ANTHROPIC_API_KEY` |
| Images | Pillow + `piexif` (EXIF GPS/time), `imagehash` (perceptual hash) |
| Media | Local `/media` folder behind a `StorageAdapter`; serve through short-lived signed URLs |
| Frontend | **React + Vite + TypeScript**, React Router, plain CSS / CSS modules. **No Tailwind UI kits, no shadcn, no Material UI** (they look like SaaS/AI apps; see Section 10) |
| Maps | Leaflet + OpenStreetMap tiles, `leaflet.heat` |
| Charts | Chart.js |
| i18n | `react-i18next`, English + Kannada (Kannada on **citizen pages only**) |
| Tests | pytest (+ `freezegun`), one Playwright end-to-end test |
| Run | Docker Compose services: `db`, `api`, `web`, `simulator` |

---

## 4. Architecture

```
Citizen Portal (gov-style web)      Officer Console      Field Team (mobile web)      Control Room
            \                              |                     |                         /
             +---------------------------- FastAPI (REST) -----------------------------+
                                           |
              Domain modules: complaints · workflow · work_orders · sla · wards · assets
                              crews · notifications · media · audit · ingestion · incidents
                                           |
                     Event bus (pub/sub + events table) <----> Scheduler
                                           |
     +------------------------------ AGENT LAYER ------------------------------------+
     |  Shared Agent Runtime: tool registry · Claude tool-use loop · decision log     |
     |  · rule fallback · record/replay cache · timeout & step limit                  |
     |                                                                                |
     |  1 Case Investigator   2 Follow-up & Escalation   3 Road Hazard Sensing         |
     |  4 Evidence Auditor    5 Surge Commander                                        |
     |  Shared tool used by all agents: notify_citizen()                              |
     +--------------------------------------------------------------------------------+
                                           |
                  PostgreSQL + PostGIS · /media · simulated adapters
          (vehicle OEM feed, SMS/WhatsApp outbox, weather, external agencies)
```

**Design rule:** agents **propose, and act only on safe, reversible steps**. Deterministic code enforces the rules: status transitions, permissions, SLA clocks, the audit log. **No agent may reject or close a complaint by itself.**

---

## 5. The agents (most important section)

### 5.1 Shared Agent Runtime (build this first, then every agent uses it)

Folder: `backend/app/agents/runtime/`

- `Agent` base class: `name`, `system_prompt`, `tools` (a list of registered Python functions with JSON schemas), `trigger` (event names or a schedule), `max_steps` (default 8), `timeout_s` (default 30), `fallback()`.
- **Tool registry:** decorator `@tool(name, description, schema)`. Tools are ordinary Python functions that query the DB or call adapters. Every tool returns small JSON (no huge payloads).
- **Run loop:** Claude tool use. Call the model, run any tool calls it asks for, return the results, and repeat until it gives a final answer or hits `max_steps`. The final answer must be **structured JSON validated against a Pydantic model** for that agent. If it fails validation, retry once, then use the fallback.
- **Decision log:** every run writes an `agent_runs` row (agent, trigger, input summary, status, model or `"rules"`, latency, final output JSON, rationale, confidence 0–1) and one `agent_steps` row **per tool call** (tool name, args, result summary). The Agent Activity Log UI reads these.
- **Human override tracking:** when an officer overrides an agent proposal, store it on the run (`overridden_by`, `override_reason`).
- **Fallback:** if there's no API key, or on a timeout, error or invalid output, run the agent's rule-based `fallback()` and log `model = "rules"`.
- **Record/replay cache:** env `AGENT_MODE = live | record | replay`. In `record` mode, save each model request/response keyed by a hash of (agent, input). In `replay` mode, serve the saved response, so the demo is fast and doesn't depend on the network or rate limits. `make demo` uses replay if a cache exists.
- **Shared tool `notify_citizen(sr_id, event, extra)`:** writes a short, polite, plain-language message in the citizen's language (English/Kannada) to the `notifications` outbox. Use templates; the LLM may polish wording. Every agent uses this, so citizens are always told what's happening and why. No separate communication agent.

### 5.2 Agent 1: Case Investigator (fixes "routing is slow")

- **Trigger:** `complaint.submitted` (and `complaint.reopened`).
- **Goal:** investigate a new complaint like a senior ward engineer would, and produce a **triage brief**.
- **Tools:**
  - `get_ward_for_location(lat, lon)`
  - `find_nearby_assets(lat, lon, type, radius_m)`
  - `get_asset_history(asset_id)` (past complaints and repairs)
  - `find_nearby_open_complaints(lat, lon, category, radius_m, hours)`
  - `get_planned_works(lat, lon, radius_m)` (metro, road-digging, pipeline projects)
  - `get_asset_owner(asset_id)` (municipal vs BESCOM vs BWSSB)
  - `get_sensitive_places_nearby(lat, lon, radius_m)` (school, hospital, market, bus stand)
  - `get_vehicle_detections_nearby(lat, lon, radius_m, days)` (from Agent 3's data)
  - `get_sla_policy(category, priority)`
  - `get_officer_workload(ward_id, department_id)`
  - `analyze_photo(attachment_id)` (vision: what's in the photo; does it match the chosen category?)
- **Output (Pydantic `TriageBrief`):** `category` (may correct the citizen's choice), `priority` P1–P4, `department_id`, `ward_id`, `suggested_officer_id`, `asset_id?`, `duplicate_of?` + `duplicate_confidence`, `repeat_failure` bool + note, `planned_work_conflict?`, `interagency_referral?` (agency + reason), `rationale` (3–5 short bullet points a human can read), `confidence`.
- **Acts on its own:**
  - Places the complaint in the right ward/department queue.
  - Auto-merges duplicates when confidence ≥ 0.9 (same category, ≤ category radius 25–100 m, within 72 h, text or photo similar). The citizen is told it's linked and keeps receiving updates.
  - Emergency keywords ("live wire", "open manhole", "child fell", and Kannada equivalents) → P1, plus an immediate control-room alert.
  - `notify_citizen` with the acknowledgement and expected timeline.
- **Needs a human:** the ward officer clicks **Accept** (→ ASSIGNED) or **Override** (reason required). Merges under 0.9 confidence are only suggestions.
- **Fallback:** point-in-polygon ward lookup, a category→department table, a priority rule table, a radius/time duplicate check.
- **Demo moment:** a streetlight complaint → the agent finds the pole failed twice in 60 days and 2 more complaints nearby → "likely a feeder fault; owner BESCOM; refer to the agency; P2 because of the bus stand."

### 5.3 Agent 2: Follow-up & Escalation (fixes "follow-up is poor")

- **Trigger:** scheduler tick every minute (respects time acceleration, see Section 6.3), plus `referral.created`.
- **Goal:** make sure no case sits idle. Diagnose **why** a case is late and fix it before the deadline; escalate with a reason when it can't.
- **Watches:** every open complaint and work order with an SLA, and every inter-agency referral.
- **Tools:**
  - `get_case_timeline(sr_id)`
  - `get_crew_load(crew_id)`
  - `find_available_crews(ward_id, skill, radius_km)` (including the next ward)
  - `check_material_stock(item)` (seeded inventory)
  - `get_referral_status(referral_id)`
  - `send_agency_followup(referral_id, message)` (simulated agency inbox)
  - `propose_reassignment(wo_id, crew_id, reason)`
  - `raise_material_request(item, qty)`
  - `escalate(sr_id, level, reason_summary)`
  - `notify_officer(officer_id, message)`
  - `notify_citizen(...)`
- **Behaviour:**
  - At **75% of the SLA** (AT_RISK), investigate the cause: crew overloaded? material out of stock? waiting on an external agency? no one assigned?
  - Internal cause → propose a fix (e.g. "Crew W13-B is free 1.2 km away; reassign?"), notify the officer, and raise a material request if needed.
  - External agency → automatically send a follow-up message at the set interval (e.g. every 24 SLA-hours); escalate to the zonal officer after 2 follow-ups with no response.
  - **On breach** (rule engine): escalate one level (L1→L2→L3→L4) automatically. The agent writes the **reason summary** attached to the escalation ("Delayed because LED drivers were out of stock since 3 Nov, not inaction").
  - Tell the citizen the honest reason for any delay ("Waiting for BESCOM to repair the feeder; we have followed up twice").
- **Acts on its own:** agency follow-ups, notifications, material requests, escalation on breach.
- **Needs a human:** reassignment (one-click Approve in the officer console), SLA pause/waiver.
- **Rules (deterministic code, not the agent):** escalation **never resets the SLA clock**; SLA pauses only for approved reasons (waiting on citizen, external agency, weather); every pause/resume is logged; a second reopen → automatic L2 escalation.
- **Fallback:** template diagnosis from data (crew load > threshold, stock = 0, referral pending) and template messages.

### 5.4 Agent 3: Road Hazard Sensing (data collection layer, see Section 9)

- **Trigger:** clustering run every 2 minutes (accelerated in demo) after new raw detections arrive.
- **Goal:** find potholes **before anyone complains**, using connected-vehicle detections, and avoid false alarms.
- **Tools:**
  - `cluster_detections(window_days, eps_m)` (PostGIS DBSCAN)
  - `get_cluster_stats(cluster_id)` (distinct vehicles, days seen, avg confidence, avg jolt)
  - `check_known_features(lat, lon)` (speed breakers, railway crossings)
  - `find_nearby_open_complaints(...)`
  - `get_recent_repairs(lat, lon, radius_m, days)`
  - `get_road_class(lat, lon)` (arterial / local, seeded)
  - `create_system_complaint(...)`
  - `attach_corroboration(sr_id, cluster_id)`
  - `flag_repair_failure(wo_id, cluster_id)`
  - `queue_for_review(cluster_id, reason)`
- **Behaviour:**
  - Filter out clusters on known speed breakers and railway crossings, and single-vehicle clusters.
  - **Strong cluster** (≥ 3 distinct vehicles, confidence ≥ 0.8) with no complaint nearby → create a system complaint (`source = VEHICLE_FEED`, category Pothole, auto-written description). It then goes through Agent 1 like any other complaint.
  - **Open citizen complaint within 25 m** → attach as corroboration ("Confirmed by 7 connected vehicles"), which raises the priority score.
  - **Location repaired in the last 30 days** → flag the repair as possibly failed and mark the contractor/crew for quality review.
  - **Weak/ambiguous cluster** → officer review queue, with the agent's reasoning.
- **Fallback:** the same thresholds as pure rules.
- **Stretch:** "ask a field team member who is already nearby to take a confirming photo."

### 5.5 Agent 4: Evidence Auditor (proves the work was really done)

- **Trigger:** `work_order.completed` (the field team uploads an after-photo and marks it done).
- **Goal:** decide whether the completion evidence is believable, before a human approves.
- **Tools:**
  - `get_photo_metadata(attachment_id)` (EXIF time, GPS)
  - `get_work_order(wo_id)` (assignment time, location)
  - `distance_m(a, b)`
  - `compare_with_all_photos(attachment_id)` (perceptual hash against before-photo and every other job's photos)
  - `vision_compare(before_id, after_id, category)` ("Is the pothole visibly filled? Is it the same place?")
  - `get_crew_audit_history(crew_id)`
- **Checks:** after-photo taken **after** assignment; GPS within the category radius of the complaint (e.g. 50 m); not a reused photo (hash too close to any other image); vision says the issue looks fixed and it's the same scene. Missing EXIF → "unverifiable"; this needs a human, it is not an automatic fail.
- **Output (`AuditVerdict`):** `verdict` PASS / FLAG / FAIL, `score` 0–100, list of `checks` (name, passed, detail), `rationale`.
- **Acts on its own:** FAIL with clear evidence (e.g. GPS 2 km away, or reused photo) → work order to **REWORK** with the deficiency stated; the field team is notified. A crew with repeated FLAGs gets a higher audit priority.
- **Needs a human:** PASS and FLAG go to the Control Room / Executive Engineer for **Approve** → VERIFIED. The final approval is always human.
- **Fallback:** all checks except vision run as rules; vision is marked "skipped".

### 5.6 Agent 5: Surge Commander (keep it small; reuse Agent 3's clustering code)

- **Trigger:** more than N complaints (default 15) of flood/drain/waterlogging/tree-fall categories within 2 km and 60 minutes, **or** a simulated weather alert ("Heavy rain warning") plus a rising complaint rate.
- **Goal:** turn a flood of individual complaints into a few **incidents** that can be managed, and keep leadership and the public informed.
- **Tools:**
  - `get_recent_complaints(categories, minutes)`
  - `cluster_complaints(eps_m)`
  - `get_weather_alerts()` (simulated)
  - `create_incident(name, area, sr_ids, severity)`
  - `link_to_incident(sr_id, incident_id)`
  - `get_crew_availability(zone)`
  - `draft_public_advisory(incident_id)`
  - `write_situation_summary(incidents)`
  - `notify_citizen(...)` (for all linked complaints)
- **Behaviour:**
  - Group complaints into incidents by area (e.g. "Kengeri Underpass Waterlogging — 23 reports").
  - Suggest a crew allocation **as text** ("2 jetting machines needed at Incident A, 1 at B").
  - Draft a **public advisory** for the website news ticker and SMS ("Avoid Kengeri underpass; crews deployed").
  - Write a short **situation summary** for the Commissioner, refreshed every simulated hour.
  - Tell every linked citizen their complaint is part of an active incident being handled.
- **Acts on its own:** creating incidents, linking complaints, notifying citizens, drafting.
- **Needs a human:** publishing the advisory (Control Room clicks Publish → it appears in the public ticker), actual crew allocation.
- **Fallback:** a radius-based grouping rule and template summaries.
- **Stretch:** pre-positioning crews, switching to monsoon SLA rules.

---

## 6. Workflow (simple but correct)

### 6.1 Complaint (Service Request) states

`SUBMITTED → ASSIGNED → IN_PROGRESS → WORK_COMPLETED → VERIFIED → RESOLVED → CLOSED`

plus `MERGED`, `REJECTED`, `ON_HOLD`, `REOPENED`.

| From | To | Who | Required |
|---|---|---|---|
| SUBMITTED | ASSIGNED | Ward Officer (accepting the agent brief) | owner officer, department |
| SUBMITTED | MERGED | Agent 1 (conf ≥ 0.9) or Officer | parent SR id |
| SUBMITTED | REJECTED | Officer only | reason code + citizen-readable explanation |
| ASSIGNED | IN_PROGRESS | System, when the first work order starts | — |
| ASSIGNED / IN_PROGRESS | ON_HOLD | Officer | reason code (material, agency, weather, access) |
| ON_HOLD | previous state | Officer | — |
| IN_PROGRESS | WORK_COMPLETED | System, when all work orders are COMPLETED | — |
| WORK_COMPLETED | IN_PROGRESS | System, when any work order goes to REWORK | — |
| WORK_COMPLETED | VERIFIED | Control Room / EE, when all work orders are VERIFIED | approver |
| VERIFIED | RESOLVED | System (after notify_citizen with before/after photos) | — |
| RESOLVED | CLOSED | Citizen confirms, or verification window expires (`closure_type = CITIZEN` / `AUTO`) | rating optional |
| RESOLVED | REOPENED | Citizen | reopen reason |
| REOPENED | ASSIGNED | Officer, after Agent 1 re-investigates | — |
| MERGED | SUBMITTED | Officer (unmerge) | reason |

- Implement this as **one declarative transition table** and **one `transition()` function** that every status change goes through. It checks the role, the required fields, and writes the `status_events` row, the audit entry and the event.
- **Escalation is not a state.** It's an `escalation_level` (0–4) field plus an `escalations` table, shown as a badge ("Escalated L2"). The case keeps its real state and owner.
- Every open complaint has exactly **one owner**. Category/priority changes need a reason.
- `AUTO` closures are counted separately from citizen-confirmed closures in every KPI.

### 6.2 Work order states

`ASSIGNED → IN_PROGRESS → COMPLETED → VERIFIED`, plus `REWORK → IN_PROGRESS` and `ON_HOLD`.

One complaint can have several work orders (keep the data model 1-to-many; the UI can create one by default). The **inspection is merged into work-order creation**: the officer or field team fills one form (asset, root cause, scope, estimated cost, before-photo).

### 6.3 SLA & time acceleration

- SLA policies are seeded per category × priority (e.g. P1 open manhole: 4 h resolution; P2 pothole on arterial road: 5 days; P3 streetlight: 7 days; verification window: 24 h for P1, 7 days otherwise).
- SLA state: ON_TRACK / AT_RISK (≥ 75%) / BREACHED / PAUSED, computed by deterministic code.
- **Demo time acceleration:** env `TIME_SCALE` (e.g. `60` = 1 real minute is 1 SLA hour). Use one `clock` module everywhere so tests can freeze time.

---

## 7. Data model (tables)

- `users` (id, name, role, ward_id?, department_id?, crew_id?, language)
- `wards` (id, name, zone, geom MultiPolygon), `departments` (id, name)
- `service_requests` (id like `SR-2026-000123`, tracking_code, category, description, location Point, address, landmark, ward_id, department_id, asset_id?, status, priority, owner_id, parent_sr_id?, reporter_count, source `CITIZEN_WEB | VEHICLE_FEED | HELPDESK`, incident_id?, escalation_level, sla_policy_id, sla_started_at, sla_due_at, sla_paused_total, closure_type?, citizen_id?, created_at)
- `sr_reporters` (sr_id, citizen_user_id or contact, merged_from_sr_id?), so every merged reporter keeps getting updates
- `attachments` (id, sr_id?, wo_id?, kind CITIZEN/BEFORE/AFTER, path, sha256, phash, exif_lat, exif_lon, exif_time, uploaded_by, uploaded_at)
- `assets` (id like `STREETLIGHT-W12-00871`, type, location, owner `MUNICIPAL | BESCOM | BWSSB`, condition), `asset_events` (asset_id, type complaint/repair, date, note)
- `planned_works` (id, name, agency, geom, start, end)
- `sensitive_places` (name, type, location), `known_road_features` (type SPEED_BREAKER/RAIL_CROSSING, location), `road_segments` (geom, class ARTERIAL/LOCAL)
- `crews` (id, ward_id, skills[], capacity), `inventory` (item, qty)
- `work_orders` (id, sr_id, crew_id, scope, root_cause, est_cost_inr, status, assigned_at, started_at, completed_at, verified_by?, audit_verdict?)
- `referrals` (id, sr_id, agency, sent_at, followups_sent, last_followup_at, agency_status, agency_reply)
- `sla_policies`, `escalations` (sr_id, level, reason_summary, authority_id, created_at, deadline)
- `incidents` (id, name, area geom, severity, status, advisory_draft, advisory_published bool, summary)
- `feedback` (sr_id, rating, comment, reopen_reason)
- `notifications` (id, recipient, channel SMS/WHATSAPP/EMAIL, language, body, related_sr_id, created_at): the outbox
- `status_events` (**append-only**: object_type, object_id, from_state, to_state, actor_type HUMAN/AGENT/SYSTEM, actor, reason, at)
- `audit_log` (**append-only**: actor, action, object, before_json, after_json, at). Enforce append-only with a DB trigger that blocks UPDATE/DELETE.
- `events` (name, payload, at)
- `agent_runs`, `agent_steps` (see 5.1)
- Data collection: `data_sources`, `raw_detections`, `rejected_detections`, `hazard_clusters` (see Section 9)

---

## 8. Roles (4 only, seeded demo users, credentials shown on the login page)

| Role | Can do |
|---|---|
| **Citizen** | File a complaint (or anonymously with a tracking code), track it, confirm / reopen / rate |
| **Ward Officer** | See complaints **only for their ward**, read the agent brief, Accept/Override, create work orders, approve reassignments, put on hold |
| **Field Team** (crew/contractor) | See **only their work orders**, upload before/after photos, update status. **Cannot see citizen phone numbers**, cannot verify their own work |
| **Control Room** (also acts as Executive Engineer / Commissioner for the demo) | City-wide view, verify completed work, publish advisories, see escalations, Agent Activity Log, hazard map |

Plus a simple **"External Agency Inbox (Simulated)"** page, used to play BESCOM/BWSSB replying to referrals during the demo.

---

## 9. Data Collection Layer: connected-vehicle road-hazard detection

**Be honest in the UI and README:** vehicle OEM data (e.g. Ather or other EV scooter/motorcycle makers) is not publicly available. This prototype uses a **simulated OEM feed** that follows a documented API contract, showing how a partner would integrate.

**Sources:**
1. Simulated connected-vehicle feed (main source).
2. Citizen complaints with photos (already in the main flow).
3. Photo-based pothole detection through `analyze_photo`.

**Ingestion API**
- `POST /api/v1/ingest/detections`: JSON batch (≤ 1,000 records), header `X-API-Key` (per data source), header `Idempotency-Key`.
- `POST /api/v1/ingest/detections/csv`: bulk import.
- Record:
  ```json
  {
    "source_record_id": "oem-sim-000123",
    "lat": 12.9081, "lon": 77.4874,
    "hazard_type": "POTHOLE | DAMAGED_ROAD | ROUGH_SURFACE",
    "detected_at": "2026-11-05T09:12:44+05:30",
    "confidence": 0.82,
    "speed_kmph": 32,
    "vertical_accel_peak_g": 1.9,
    "vehicle_ref": "salted-hash-rotated-daily",
    "image_url": null
  }
  ```
- **Validate & normalise:**
  - inside the city boundary;
  - timestamp not in the future and not older than 30 days;
  - confidence 0–1 (default 0.5);
  - map hazard_type to the internal enum;
  - de-duplicate on (source, source_record_id).
  - Keep the original payload as `raw_payload` JSON.
  - Failed records go to `rejected_detections` with a reason; **never silently dropped**.
- **Privacy:** never accept VIN, rider name, phone or full trip traces. Only hazard points, plus a rotating hashed vehicle reference used to count distinct vehicles.
- **Pipeline:** `Source → Ingestion API → Validation/Normalisation → raw_detections → Agent 3 (clustering) → hazard_clusters → complaint pipeline`.

**Simulator** (`simulator/`, own container). It posts data around Kengeri / RR Nagar (about lat 12.88–12.95, lon 77.46–77.55):
- ~15 true potholes hit by many vehicles (GPS noise ±5–8 m);
- ~5 known speed breakers (must be filtered);
- random single-vehicle noise;
- **1 pothole near an existing citizen complaint** (corroboration);
- **1 recently repaired spot that starts getting hits again** (repair failure);
- **a "rain burst" mode** that files ~25 flood/drain complaints in one area and raises a weather alert (for Agent 5).

Modes: `--once`, `--stream --rate 5`, `--scenario rain`.

**UI:** Control Room → **Road Hazard Map**, showing raw detections (small dots, toggle), clusters (circle size = distinct vehicles), and complaints created from them. Plus a small "Data Sources" table: last ingestion time, accepted/rejected counts.

---

## 10. UI: must look like an Indian government portal, NOT an AI app

**Never:**
- a chat box as the main screen;
- gradients, glassmorphism, purple, neon;
- big rounded cards with soft shadows;
- emoji, sparkle/"✨ AI" icons;
- dark mode by default;
- the shadcn/Tailwind/Material look.

The AI works behind the scenes. In the UI, call its output **"System Analysis"**, **"System Suggestion"** or **"Auto-check result"**.

**Follow the style of GIGW (Guidelines for Indian Government Websites):**

**Public page frame (build once, every page inherits it):**
1. **Top strip** (thin, dark navy): "Government of Karnataka (Demo)" | Skip to main content | Screen Reader Access | **A- A A+** | high-contrast toggle | **English / ಕನ್ನಡ**.
2. **Header** (white):
   - **left:** an **original, generic circular municipal crest drawn as SVG**. **Do NOT use the State Emblem of India or the Karnataka emblem**; their use is legally restricted;
   - **next to it:** the bilingual name "CivicFlow Municipal Corporation / ಸಿವಿಕ್‌ಫ್ಲೋ ಮಹಾನಗರ ಪಾಲಿಕೆ" with the subtitle "Citizen Grievance Redressal Portal";
   - **right:** "Helpline: 1800-000-0000 (Demo)" and a search box.
3. **Navigation bar** (solid navy ~`#1b3a6b`, white text, square edges): Home | About Us | Lodge Grievance | Track Grievance | Citizen Charter | Ward Directory | FAQs | Contact Us | Login ▾.
4. **"What's New" ticker:** scrolling, with a small red "NEW" label. Published Surge Commander advisories appear here.
5. **Footer** (dark):
   - link columns: Website Policies, Hyperlinking Policy, Copyright, Privacy, Terms, Accessibility Statement, Help, Sitemap, Feedback;
   - "Content owned by CivicFlow Municipal Corporation (Hackathon Prototype)";
   - "Last Updated: date";
   - "Visitors: count".
6. A thin banner on every page: **"Hackathon prototype — not an official government website."**

**Style:**
- **Colours:** navy primary, white background, grey panels `#f2f2f2`, saffron accent `#e87722` for headings and the active menu item, green = resolved, red = breached. Flat colours only.
- **Type:** Arial / Noto Sans / Noto Sans Kannada, 14–15 px base. Headings have a coloured left border or underline bar.
- **Shapes:** 0–3 px corners, 1 px grey borders, **breadcrumbs** on every inner page.
- **Tables** for every list: bordered, zebra rows, navy header row, "S.No." column, pagination ("Showing 1–10 of 245"), an "Export" button (CSV is fine).
- **Forms** like government forms:
  - fieldsets with legends (Grievance Details / Location Details / Contact Details);
  - red asterisk on required fields;
  - a simple math **CAPTCHA**;
  - declaration and consent checkboxes;
  - Submit + Reset buttons.

**Demo-path screens (polish these):**
- **Home:** banner area, quick-service tiles with simple line icons (Lodge Grievance, Track Status, Report Pothole, Citizen Charter, Ward Officers), a statistics strip (Total, Resolved, Within SLA %, Avg. days), and Notices/Important Links boxes.
- **Lodge Grievance:** category, description, photo upload (keep EXIF), Leaflet map pin (auto-GPS + drag to adjust), landmark, contact/anonymous, CAPTCHA.
- **Acknowledgement Slip:** a bordered box with Grievance No., date/time, category, ward, department, expected resolution date, and a **Print** button.
- **Track Grievance:**
  - enter Grievance No. + mobile/tracking code;
  - see a status table plus a vertical timeline (date / stage / remarks), including agent actions in plain words ("System linked your complaint with 2 similar reports");
  - before/after photos;
  - **Confirm Resolution / Reopen** buttons and a star rating.
- **Officer Console** (e-Office/ERP style):
  - left vertical menu; top bar with name, designation, ward, Logout;
  - complaint queue table with an SLA countdown column ("2d 4h left" green / "Breached by 6h" red);
  - an escalation badge;
  - a **"System Analysis" panel** showing the triage brief, the rationale bullet points, an expandable "Steps taken" list (tool calls), and **Accept / Override** buttons;
  - pending reassignment proposals with Approve.
- **Field Team** (mobile-friendly): My Jobs list, job detail, Start, Upload Before/After photo, Mark Completed; show the rework reason when sent back.
- **Control Room:** bordered panels for:
  - live map;
  - P1 queue;
  - SLA breach list;
  - escalations;
  - **Agent Activity Log** (table: time, agent, trigger, decision, confidence, model/rules, overridden?; click to see each tool call and the rationale);
  - Road Hazard Map;
  - Incidents with advisory Publish button and situation summary;
  - verification queue with the Auditor verdict, check list and Approve/Reject.
- **Accessibility:** WCAG 2.1 AA contrast, keyboard navigation, alt text, aria labels, large touch targets on the Field Team screens.

---

## 11. Demo story (`make demo` seeds this and prints the steps with logins)

1. **A citizen (Kannada UI)** reports a pothole near a school with a photo → acknowledgement slip.
2. **Agent 1** investigates. The Activity Log shows its tool calls: ward, nearby school, history. Two more citizens report the same pothole → auto-merged, reporter count 3, priority P2.
3. **The simulator** streams vehicle data → **Agent 3** confirms the citizen pothole ("7 vehicles") and creates a **new complaint on an arterial road that no one reported**. Speed breakers are visibly filtered on the map.
4. **A streetlight complaint** → Agent 1 finds a repeat failure + BESCOM ownership → a referral is created. **Agent 2** sends follow-ups; with time acceleration, no agency reply leads to an L2 escalation with a written reason. Then the officer plays BESCOM in the Agency Inbox and replies.
5. **The officer accepts the pothole brief** → work order → the Field Team uploads an after-photo **taken 2 km away** → **Agent 4** FAILS it with reasons → REWORK → the correct photo → PASS → Control Room approves → the citizen gets before/after photos and confirms with 5 stars.
6. **Agent 2** at 75% SLA on another job: the crew is overloaded and material is out of stock → it proposes the next ward's crew → the officer approves → the citizen is told the honest reason for the delay.
7. **Rain scenario** → ~25 flood complaints → **Agent 5** groups them into 2 incidents, drafts an advisory → Control Room publishes → it appears in the website ticker; the situation summary is shown.
8. **Control Room** shows KPIs: total reports vs unique issues, SLA compliance, reopen rate, auto-closed counted separately.

Record the agent responses once (`AGENT_MODE=record`) so the live demo can run in `replay` mode.

---

## 12. 24-hour build plan with checkpoints

| Hours | Checkpoint | Done when |
|---|---|---|
| 0–1 | **C0: Plan approved** | `docs/BUILD_PLAN.md` approved by me |
| 1–7 | **C1: Platform core** (run in parallel: backend / frontend / seed + simulator) | DB + PostGIS, migrations, **rich seed data**, 4 roles + login, transition table + `transition()` + audit, event bus, clock with TIME_SCALE, government UI frame, Lodge → Acknowledgement → Track working, officer queue, field team upload |
| 7–9 | **C2: Agent runtime + Agent 1** | Runtime (tools, loop, logging, fallback, record/replay, notify_citizen) works; filing a complaint produces a triage brief visible in the System Analysis panel and the Activity Log |
| 9–16 | **C3: Agents 2–5** (two people in parallel: Sensing → Surge; Auditor → Follow-up) + Control Room UI | Each agent triggers correctly and shows up in the Activity Log; ingestion API + simulator + hazard map working |
| 16–19 | **C4: Integration** | The whole demo story (Section 11) runs end to end |
| 19–21 | **C5: Hardening** | Tests green, bugs fixed, replay cache recorded. **Feature freeze at hour 21** |
| 21–24 | **C6: Demo prep** | README, `docs/AGENTS.md` with a Mermaid diagram, demo script, backup demo video recorded |

If behind schedule, cut in this order: Agent 5 stretch items → hazard map raw-dot layer → Kannada → export buttons → charts. **Never cut:** the agent runtime, the Activity Log, Agents 1/3/4, or the end-to-end flow.

---

## 13. Step 0: what to give me before coding

(Done: see `docs/BUILD_PLAN.md`.)

---

## 14. Tests (keep focused)

- **pytest:**
  - every allowed transition works and forbidden ones are rejected (parametrised from the table);
  - scoping rules (Ward 12 officer can't see Ward 7; field team can't see the citizen phone or verify its own work);
  - SLA states with frozen time, escalation doesn't reset the clock, pause excluded;
  - duplicate rule cases;
  - every Auditor check (old photo, far GPS, reused hash, missing EXIF);
  - ingestion validation + dead-letter;
  - clustering filters speed breakers;
  - every agent falls back to rules when the LLM raises an error.
- **Playwright (1 test):** citizen files → brief accepted → work order → after-photo → audit PASS → approve → citizen confirms → CLOSED.
- `make test` runs everything.

---

## 15. Deliverables

- `docker compose up`, `make seed`, `make demo`, `make test`
- `README.md`: setup, demo logins, what's simulated, architecture diagram, "future scope"
- `docs/BUILD_PLAN.md`, `docs/AGENTS.md`, `docs/API.md` (link to FastAPI `/docs` + the ingestion contract), `docs/DEMO_SCRIPT.md`
- `PROGRESS.md`, updated at each checkpoint
