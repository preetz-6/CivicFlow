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

## Machine B (web / simulator / docs)
