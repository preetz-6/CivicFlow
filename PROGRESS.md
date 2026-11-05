# CivicFlow — Progress

| Checkpoint | Status |
|---|---|
| C0 Plan approved | Done |
| C1 Platform core | In progress |
| C2 Agent runtime + Agent 1 | — |
| C3 Agents 2–5 + Control Room | — |
| C4 Integration | — |
| C5 Hardening | — |
| C6 Demo prep | — |

## Machine A (backend)
- **C1a foundation (written, imports OK, DB tests not yet run: no Docker on Machine A yet)**
  - docker-compose (db PostGIS 16, api, web, simulator[profile sim]), Makefile + `scripts/cf.ps1`, `.env.example`
  - 37 tables (`backend/app/models/`), migration `0001` (create_all + sequences + append-only triggers)
  - `core/clock.py` (TIME_SCALE, freeze/advance, persisted across reloads), `core/bus.py` (publish in txn, dispatch after commit)
  - `modules/workflow/table.py` (25 rules), `transition()` with role + scope + required-field checks, SLA pause/resume, WO→SR cascade, status_events + audit + citizen timeline
  - Auth: `GET /auth/demo-users`, `POST /auth/login` → `otp_demo`, `POST /auth/verify` (cookie set on response), `/auth/me`, `/auth/logout`
  - `tests/test_workflow.py`: parametrised from the table (every allowed, every forbidden, every wrong actor), scoping, cascade, SLA pause, bus commit semantics, append-only

- **C1b backend core: done, 275 pytest green, API runs in Docker**
  - **DB host port is 5433** (this laptop has a local Postgres on 5432). Containers still use `db:5432`.
  - Seed: `python -m app.seed.build --reset --demo` (4 wards, 169 assets, 272 SRs, crews/inventory, every demo hook). Coordinates: `GET /api/v1/demo/points` and `backend/app/seed/data/demo_points.json`.
  - Endpoints live (see http://localhost:8000/docs):
    - Citizen: `POST /complaints` (multipart: category, description, lat, lon, landmark, contact_name, contact_phone, anonymous, language, photo) → AckSlip · `GET /complaints/track?no=&code=` (code = tracking code OR mobile) · `POST /complaints/{id}/confirm {code?, rating, comment}` · `/reopen {code?, reason}` · `GET /my/complaints`
    - Officer: `GET /officer/queue?status=&priority=&category=&sla=&q=&page=&page_size=` (each row has `sla.label` like "2d 4h left" / "Breached by 6h") · `GET /officer/stats` · `GET /complaints/{id}` (detail, `analysis` = System Analysis once C2 lands, `allowed_actions`) · `POST .../accept` · `/override {reason, category?, priority?, merge_into?}` · `/hold {reason_code}` · `/resume` · `/reject {reason_code, explanation}` · `/merge/{parent}` · `/unmerge` · `GET /crews?ward=` · `POST /complaints/{id}/work-orders` (multipart: crew_id, scope, root_cause, est_cost_inr, before_photo)
    - Field: `GET /field/jobs` · `GET /field/jobs/{id}` · `POST .../start` · `POST .../photos` (multipart kind=BEFORE|AFTER, photo) · `POST .../complete` (409/422 with `detail` if not allowed)
    - Control: `GET /control/verification` · `POST /work-orders/{id}/approve` · `/reject {reason}`
    - Public: `/public/stats` · `/public/ticker` · `/public/categories` · `/public/wards?geometry=true` · `/public/departments`
    - Simulated: `GET /agency/inbox` · `POST /agency/referrals/{id}/reply {status, message}` · `GET /notifications` (outbox)
    - Demo: `GET /clock` · `POST /demo/clock/advance {hours}`
    - Errors are `{"detail": "..."}` with 400/403/404/409/422.
  - SLA engine: sweep every 15 s (state changes → `sla.at_risk`/`sla.breached` events), escalation L1–L4 on breach (never resets the clock), auto-close after the verification window, second reopen → L2.

- **C2 agent runtime + Agent 1 (Case Investigator): done**
  - Runtime `backend/app/agents/runtime/`: `@tool` registry (every call logged to `agent_steps`; rule-based steps are prefixed `rule:`), manual Claude tool-use loop (`loop.py`, max 8 steps, timeout, JSON output validated by Pydantic with one retry), fallback to rules on no key / error / timeout / refusal / invalid output / replay miss, record/replay cache (`adapters/llm.py`, per-turn keys in `backend/agent_cache/`), shared `notify_citizen` tool, server-side refusal fallback enabled on the Claude API.
  - Agent 1 triggers on `complaint.submitted` / `complaint.reopened`. It acts alone on: queue placement (department, priority, asset), auto-merge at ≥0.9 confidence, referral DRAFT (sent on officer Accept), acknowledgement SMS, P1 control-room alert. Ward is always point-in-polygon; the model can't move it.
  - **For the System Analysis panel:** `GET /complaints/{id}` → `analysis` = `{run_id, agent, status ("OK"|"FALLBACK"), model ("claude-…"|"rules"|"replay:…"), confidence, decision, rationale ("- bullet\n- bullet"), output (TriageBrief: category, priority, department_id, ward_id, asset_id, duplicate_of, duplicate_confidence, repeat_failure, repeat_failure_note, planned_work_conflict, interagency_referral{agency,reason}, vehicle_corroboration, rationale[], citizen_summary, confidence), steps:[{idx, tool, args, result, error}], overridden, override_reason, accepted}`. Buttons: `POST /complaints/{id}/accept` and `/override {reason, ...}`. Label it "System Analysis", and show "Rule-based analysis" when `model == "rules"`.
  - **For the Agent Activity Log:** `GET /agent-runs?agent=&subject_id=&overridden=&page=&page_size=` → `items[{id, at, agent, agent_label, trigger, subject_id, decision, confidence, model, mode, status, latency_ms, overridden, overridden_by, override_reason, accepted}]` · `GET /agent-runs/{id}` (rationale + steps + input + error) · `GET /agent-stats`.

## Machine B (web / simulator / docs)
- **Step 1: Vite scaffold + government frame (built, `npm run build` passes; not yet seen against the real API)**
  - `web/`: React 18 + Vite + TS, React Router, react-i18next (EN + Kannada), plain CSS with `styles/tokens.css` (navy/saffron, flat, 0-3 px corners, AA contrast, high-contrast overrides). Vite proxies `/api` and `/media` to `VITE_API_TARGET` (default `http://localhost:8000`).
  - Frame on every public page: top strip (Skip to main content, Screen Reader Access, A-/A/A+, high contrast, English/ಕನ್ನಡ, all saved in localStorage), original SVG crest (not the State Emblem or the Karnataka emblem), bilingual header with helpline, navy nav bar (mobile menu), prototype banner, "What's New" ticker with Pause, dark footer with Last Updated (build date).
  - Shared UI: `Table` (S.No., zebra, navy header, "Showing x–y of n", Previous/Next, CSV export with BOM; client or server pagination), `Fieldset`/`Field` (red asterisk), math `Captcha`, `StatusTag`/`PriorityTag`/`EscalationBadge`, `SlaBadge` (uses the backend clock), `Timeline`, `Breadcrumbs`. Staff `ConsoleLayout` (top bar with name, designation, ward, Logout; left menu; redirects to /login without a session) is ready for step 2.
  - Pages: Home (welcome + notices), About, Citizen Charter, FAQs, Contact, 5 policy pages, Accessibility Statement, Help, Screen Reader Access, Sitemap, 404. Static bodies are English only (a Kannada note says so).
  - Not rendered until they work: nav items Lodge / Track / Ward Directory / Login (step 2), header search (needs Track), footer Visitors count (needs B-2), ticker (hidden until `GET /public/ticker` exists; mocked in `npm run dev:mock`).
  - Kannada strings were machine-assisted: **needs review by a Kannada reader**.
  - Requests for Machine A: `docs/REQUESTS_FOR_A.md` (B-1 ticker, B-2 visitor counter, B-3 SLA policies for the charter).
