# Requests from Machine B to Machine A

Machine B never edits `backend/`. Backend changes the web app needs are listed here; the human passes them to Machine A. Mark an item **Done** (with the commit) when it ships.

| # | Request | Why | Status |
|---|---|---|---|
| B-1 | `GET /api/v1/public/ticker` → `[{id: str, text: str, published_at: datetime}]`, newest first. Include published Surge Commander advisories plus any seeded notices. No auth. | "What's New" ticker on every public page. Until it ships, the ticker is hidden in real-API mode and mocked in `npm run dev:mock`. | **Done** (Machine A, C2 follow-up). Item shape: `{id, text, text_kn, new, published_at}` |
| B-2 | A real visitor counter, e.g. `visits` in `GET /public/stats`, incremented once per browser session by `POST /api/v1/public/visit`. | The GIGW footer shows "Visitors: N". It stays hidden until there is a real number. | **Done**: `POST /public/visit` → `{visits}`; `GET /public/stats` has `visits` |
| B-3 | `GET /api/v1/public/sla-policies` → `[{category, priority, resolution_hours}]` from the seeded `sla_policies`. | The Citizen Charter page currently shows indicative values from the brief. It should show the seeded policies so the charter and the SLA engine agree. | **Done**: also returns `category_label`, `verification_hours` |
| B-4 | **Blocker.** Commit `backend/app/modules/media/`. The root `.gitignore` line `media/` also matches that package, so it never reached GitHub, and the api container crashes on start with `ModuleNotFoundError: No module named 'app.modules.media'`. Fix: change the line to `/media/` (and `backend/media/` if that is the upload folder), then `git add backend/app/modules/media` and push. | Machine B cannot start the API, generate types or test step 2 against the real backend. | Open |
