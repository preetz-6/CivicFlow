# Kickoff for Machine B (paste this to Claude Code on the second laptop)

You are **Machine B** on the CivicFlow hackathon build. A second Claude Code instance (**Machine A**) is building the backend at the same time.

Read these before you write any code:
1. `docs/BRIEF.md`: the full product brief (the specification).
2. `docs/BUILD_PLAN.md`: the approved plan. Pay most attention to §3 (folders and ownership), §9 (task split), §10 (API surface) and §12 (cuts).

## Your ownership (hard rule)
- You own **`web/`**, **`simulator/`**, **`docs/`** (except BUILD_PLAN.md), `README.md`, and the Playwright test in `web/e2e/`.
- **Never edit `backend/`, `docker-compose.yml`, `Makefile` or `alembic/`.** If you need a backend change, write it in `docs/REQUESTS_FOR_A.md` and tell your human. They will pass it to Machine A.
- Git: work on `main`, make small commits, `git pull --rebase` before every push. Append to `PROGRESS.md` under a "Machine B" heading.

## Stack (approved)
React 18 + Vite + TypeScript, React Router, plain CSS (CSS variables in `web/src/styles/tokens.css`) and CSS modules, `react-i18next`, Leaflet + `react-leaflet` + `leaflet.heat`, Chart.js, `openapi-typescript` (dev dependency), Playwright.
**No Tailwind, no shadcn, no Material UI, no component kits.** It must look like an Indian government (GIGW) portal. Brief §10 lists exactly what that means. No gradients, no emoji, no rounded cards, no "AI" sparkle. Agent output is labelled "System Analysis", "System Suggestion" or "Auto-check result".

## API
- Backend base URL: `http://localhost:8000/api/v1`. Vite dev server proxies `/api` and `/media` → `http://localhost:8000`. In docker the web container uses `http://api:8000`.
- Until Machine A ships each endpoint, mock it in `web/src/api/mock.ts` with the shapes in BUILD_PLAN §10. Switch with `VITE_USE_MOCKS=1`.
- Once the backend is up, run `npx openapi-typescript http://localhost:8000/openapi.json -o src/api/schema.d.ts` and use those types.
- Auth: cookie session (`credentials: "include"`). Login is two steps: `POST /auth/login {username}` returns `{otp_demo}` to show on screen, then `POST /auth/verify {username, otp}`.
- Demo users: `citizen1` (Kannada UI), `citizen2`, `citizen3`, `officer.w12`, `officer.w13`, `zonal.west`, `field.w12a`, `field.w12b`, `field.w13a`, `field.w13b`, `control`. List them on the login page.
- Statuses, roles and priorities are UPPER_SNAKE strings exactly as in brief §6/§8.

## Your order of work (matches BUILD_PLAN §9)
1. **Now, 0–1.5h:** Vite scaffold in `web/`, `tokens.css`, and the full public frame: top strip (A-/A/A+, high contrast, EN/ಕನ್ನಡ), an **original** SVG crest (NOT the State Emblem or the Karnataka emblem), the bilingual header, the navy nav bar, the "What's New" ticker, the dark footer, the prototype banner and breadcrumbs. Shared `Table` (S.No., zebra, navy header, pagination text, CSV export), `Fieldset`, `Captcha` (simple math), `StatusTag`, `SlaBadge`, `Timeline`. Also an inner "console" layout for staff (left menu, top bar with name, designation, ward, Logout).
2. **1.5–7h:** Home, Lodge Grievance (Leaflet pin with auto-GPS and drag, photo upload sent as the original file so EXIF survives), Acknowledgement Slip (Print), Track Grievance (status table, vertical timeline, before/after photos, Confirm/Reopen, stars), Login, Officer queue + case detail, Field Team (My Jobs, job detail, Start, upload Before/After, Mark Completed, rework reason; large touch targets).
3. **7–9h:** System Analysis panel (brief, rationale bullets, expandable "Steps taken", Accept / Override with a reason), Agent Activity Log table + drill-down.
4. **9–16h:** `simulator/` (Python, its own Dockerfile; posts to `POST /api/v1/ingest/detections` with `X-API-Key` and `Idempotency-Key`; modes `--once`, `--stream --rate 5`, `--scenario rain`; scenario details in brief §9 and seed coordinates in BUILD_PLAN §8. Ask Machine A for the exact coordinates file `backend/app/seed/data/demo_points.json`). Then the Control Room panels: map, P1 queue, breaches, escalations, Activity Log, Road Hazard Map (raw dots toggle, clusters sized by distinct vehicles, filtered speed breakers greyed out), Incidents + Publish, verification queue with Auditor checks + Approve/Reject, Data Sources table, reassignment approvals, External Agency Inbox (Simulated), Kannada strings for the citizen pages.
5. **16–24h:** integration, Playwright happy-path test (brief §14), `README.md`, `docs/AGENTS.md` (Mermaid), `docs/DEMO_SCRIPT.md`.

Checkpoint behaviour: at each checkpoint, tell your human what works and how to see it, update `PROGRESS.md`, and wait for "continue".
