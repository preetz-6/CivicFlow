# CivicFlow: Agentic Civic Operations System

> **Hackathon prototype, not an official government website.** "CivicFlow Municipal Corporation" is fictional; the demo geography is Kengeri / Rajarajeshwari Nagar, Bengaluru. All data is synthetic, and everything marked **(Simulated)** is simulated.

Problem statement DL-SJBIT-HK26-SSF009: an agentic civic operations system for smart cities.

City corporations get thousands of complaints (potholes, garbage, broken streetlights, water leaks, blocked drains). Routing them is slow and manual, nobody chases stuck cases or silent agencies, and citizens never learn what happened. CivicFlow puts **five AI agents** on top of a deterministic workflow engine. They investigate, route, chase, verify and coordinate each issue from report to verified closure, and **humans approve every decision that affects a citizen's case**.

Citizen journey: report → acknowledgement slip → track progress → before/after photos → confirm or reopen → closed.

## The five agents

| Agent | What it does | Human decision |
|---|---|---|
| **1 Case Investigator** | Investigates every new complaint like a senior ward engineer: ward, nearby assets and their history, duplicates, sensitive places, planned works, asset owner (municipal / BESCOM / BWSSB) → a triage brief | Officer **Accept / Override** |
| **2 Follow-up & Escalation** | At 75 % of the SLA works out *why* a case is late (crew overloaded, material out, agency silent), proposes a fix, chases agencies, escalates with a written reason, tells the citizen the honest reason | Officer **Approve** reassignment |
| **3 Road Hazard Sensing** | Clusters connected-vehicle detections (PostGIS DBSCAN), filters speed breakers, confirms citizen complaints, creates complaints nobody filed, flags failed repairs | Officer reviews weak clusters |
| **4 Evidence Auditor** | Checks completion photos: taken after assignment, at the site, not reused, issue visibly fixed. Sends work back on hard evidence | Control Room **Approve** (always human) |
| **5 Surge Commander** | Turns a flood of rain complaints into a few incidents, suggests crews, drafts a public advisory and a situation summary | Control Room **Publish** |

Every run is logged with each tool call, its rationale and confidence, and whether a human overrode it: see the **Agent Activity Log**. Details and diagrams: [docs/AGENTS.md](docs/AGENTS.md).

The app works **without any LLM API key**: every agent has a rule-based fallback, and `AGENT_MODE=replay` serves recorded answers for a fast, offline demo.

## Quick start

Requirements: Docker Desktop (WSL2 on Windows). For the end-to-end test also Node 20+.

```bash
cp .env.example .env          # optional: add ANTHROPIC_API_KEY; without it agents use rules
docker compose up -d --build  # db (PostGIS), api (FastAPI), web (Vite)
make demo                     # fresh demo seed (Windows: .\scripts\cf.ps1 demo)
```

| What | URL |
|---|---|
| Citizen portal and all consoles | http://localhost:5173 |
| API docs (OpenAPI) | http://localhost:8000/docs |

**Ports already in use?** Set `DB_PORT`, `API_PORT`, `WEB_PORT` in `.env` (the containers still talk to each other on 5432 / 8000). If you run the web app outside Docker (`cd web && npm install && npm run dev`), put `VITE_API_TARGET=http://localhost:<API_PORT>` in `web/.env.local`.

Windows without `make`: every Makefile target exists as `.\scripts\cf.ps1 <target>`.

## Demo logins

**Login** with User ID + password. Seeded passwords: citizens `Citizen@2026`, officers `Officer@2026`, field teams `Field@2026`, Control Room `Control@2026`.

| User ID | Role | Lands on |
|---|---|---|
| `citizen1` (Kannada), `citizen2`, `citizen3` | Citizen | Lodge Grievance (citizens can also lodge and track without logging in) |
| `officer.w12`, `officer.w13` | Ward Officer (sees only their ward) | Complaint Queue |
| `field.w12a`, `field.w12b`, `field.w13a`, `field.w13b`, ... | Field Team (sees only its jobs, never citizen phone numbers) | My Jobs |
| `control` | Control Room / Executive Engineer / Commissioner | Dashboard |

The full eight-minute walkthrough is in [docs/DEMO_SCRIPT.md](docs/DEMO_SCRIPT.md).

## Simulator (Simulated OEM feed and rain)

```bash
docker compose run --rm simulator python sim.py --once            # one pass of vehicle detections
make sim                                                          # stream ~5 detections/second
make rain                                                         # weather alert + ~25 flood complaints
```

Without Docker: `python simulator/sim.py --once --api http://localhost:8000` (standard library only). See [simulator/README.md](simulator/README.md).

## Tests

```bash
make test        # backend pytest + the Playwright end-to-end test (Windows: .\scripts\cf.ps1 test)
```

The Playwright test (`web/e2e/happy-path.spec.ts`) drives the real UI against the running stack: citizen lodges → officer accepts the System Analysis → work order → field team uploads an after-photo → Evidence Auditor PASS → Control Room approves → citizen confirms with 5 stars → CLOSED. First time only: `cd web && npm install && npx playwright install chromium`. If the web app is not on port 5173, set `E2E_BASE_URL`.

## Architecture

```mermaid
flowchart TB
  subgraph Browsers["web/ (React + Vite + TypeScript, plain CSS, GIGW style)"]
    CP[Citizen Portal<br/>English + ಕನ್ನಡ]
    OC[Officer Console]
    FT[Field Team<br/>mobile web]
    CR[Control Room]
  end
  SIM[simulator/<br/>Simulated OEM feed]
  subgraph API["backend/ FastAPI modular monolith"]
    REST[REST /api/v1]
    WF["workflow: transition table + transition()"]
    SLA[SLA engine + clock<br/>TIME_SCALE]
    BUS[(Event bus<br/>+ events table)]
    AG[Agent runtime<br/>5 agents, tool registry,<br/>decision log, fallback,<br/>record/replay]
    ING[Ingestion API]
  end
  DB[(PostgreSQL 16 + PostGIS)]
  LLM[Claude API<br/>optional]
  Browsers --> REST
  SIM --> ING
  REST --> WF --> BUS --> AG
  SLA --> BUS
  AG -->|actions via transition()| WF
  AG -.-> LLM
  WF --> DB
  ING --> DB
```

- **Status changes** go through one declarative transition table and one `transition()` function (role, scope and required-field checks; status event, audit entry and bus event in the same transaction).
- **Audit log and status events are append-only**, enforced by database triggers.
- **SLA time** runs on one clock module; `TIME_SCALE=60` makes one real minute one SLA hour, and `python scripts/ops.py advance <hours>` moves it forward on cue.

## What is real and what is simulated

| Real | Simulated |
|---|---|
| The 5 agents, runtime, Activity Log, fallbacks, record/replay | Connected-vehicle (OEM) feed: no OEM data is public; `simulator/` follows a documented ingestion contract |
| Workflow engine, SLA engine, escalation rules, append-only audit log, role and ward scoping | SMS / WhatsApp: on-screen outbox only |
| PostGIS ward lookup, radius queries, DBSCAN clustering (ward polygons approximate) | BESCOM / BWSSB replies: the **Agency Liaison** page, where staff record replies, played by the presenter |
| Photo EXIF checks and perceptual hashing; vision with an API key | Weather alerts |
| Ingestion validation and dead letter | All people, wards, assets and history are synthetic seed data |

## Repository

```
backend/     FastAPI app, agents, seed, Alembic, pytest
web/         React app (citizen portal, officer, field team, control room), Playwright test
simulator/   Simulated OEM feed and rain scenario
docs/        BRIEF, BUILD_PLAN, AGENTS, API, DEMO_SCRIPT
```

## Documentation

- [docs/AGENTS.md](docs/AGENTS.md): the agents and the runtime, with diagrams
- [docs/API.md](docs/API.md): API overview and the ingestion contract
- [docs/DEMO_SCRIPT.md](docs/DEMO_SCRIPT.md): step-by-step demo
- [docs/BUILD_PLAN.md](docs/BUILD_PLAN.md): the approved plan; [PROGRESS.md](PROGRESS.md): what was built when

## Future scope (not in this prototype)

Offline-first PWA for field teams; real SMS, WhatsApp and IVR channels; a real integration with an EV / OEM partner; a public transparency dashboard; ERP / finance and contractor billing; a separate contractor portal; multi-city support; a separate inspection stage; more roles (zonal officer, contractor, auditor); monsoon SLA rules and pre-positioning crews before forecast rain.

## Credits

Map data © OpenStreetMap contributors. The crest is an original drawing made for this prototype; it is not the State Emblem of India or the emblem of the Government of Karnataka.
