# Tasks for Machine B (from Machine A)

Pull first (`git pull --rebase`). Machine A changed `web/` while you were away: password login, removed every
"demo / simulated / prototype / helpline" text, removed the demo clock and demo photo links, renamed the
Agency Inbox to **Agency Liaison**. Read the last commits before editing. Then rebuild:
`docker compose up -d --build` and `docker compose restart web` (on Windows the web container does not always
see file changes; restart it after a pull).

Machine A owns `backend/`. You own `web/`. Backend endpoints below are being built now; mock them until the
commit "agent-ops feed" lands.

## B-T1. Remove citizen login entirely

Citizens never log in. They lodge (no account) and track with **Grievance No. + mobile or tracking code**.
- Backend (Machine A): `POST /auth/login` now refuses CITIZEN accounts (401 "Citizens do not need to log in:
  use Track Grievance"). `GET /my/complaints` is removed. `POST /complaints/{id}/confirm` and `/reopen` take
  `{code, ...}` (tracking code or mobile) and need no session.
- Web: nav "Login" → **"Staff Login"** (EN: Staff Login, KN: ಸಿಬ್ಬಂದಿ ಲಾಗಿನ್). Remove any citizen landing page /
  "My complaints" view and every place that assumes a logged-in citizen. Track Grievance: Confirm / Reopen send
  the code the citizen typed. Login page text: staff only ("Login for Corporation staff").
- Playwright: the citizen steps use Lodge + Track with the code (no citizen login).

## B-T2. Remove the policy pages

Delete Website Policies, Hyperlinking, Copyright, Privacy, Terms of Use, Help and Sitemap pages and the footer
link columns pointing to them. Keep: About Us, Citizen Charter, Ward Directory, FAQs, Contact Us,
Accessibility Statement (one line in the footer is enough), Screen Reader Access (GIGW). Footer becomes one
short row: "© CivicFlow Municipal Corporation · Accessibility · Visitors: N".

## B-T3. Agent Operations (Control Room) — the centrepiece of the demo

Purpose: show what a normal website cannot: **things happening that nobody clicked.** The presenter keeps this
page on one half of the screen while playing the citizen / field crew on the other half.

Route `/control/operations`, first item in the Control Room menu, label **"Agent Operations"**.

### Data
`GET /api/v1/agent-ops/feed?limit=80` (Control Room session). Poll every 2 s. Newest first. Each item has a
stable `key`; diff by key so items animate in and RUNNING runs update in place.

```ts
type OpsItem =
  | { kind: "agent_run"; key: string; at: string; id: number; agent: string; agent_label: string;
      status: "RUNNING" | "OK" | "FALLBACK" | "ERROR"; model: string | null;   // "rules" | "gemini-…" | "replay:…"
      trigger: string;                                                           // e.g. "complaint.submitted"
      cause: Cause;                                                              // what started it (see below)
      subject_type: string | null; subject_id: string | null;
      decision: string | null; confidence: number | null; latency_ms: number | null;
      steps: { idx: number; tool: string; kind: "lookup" | "rule" | "action"; label: string; summary: string }[];
      guardrails: string[];   // e.g. "P1 capped to P2 (no emergency keywords)", "FAIL downgraded: no hard evidence"
      human: { accepted_by: string | null; overridden_by: string | null; override_reason: string | null } }
  | { kind: "human"; key: string; at: string; actor: string; role: string; text: string; subject_id: string | null }
  | { kind: "citizen"; key: string; at: string; text: string; subject_id: string }   // a grievance was lodged
  | { kind: "feed"; key: string; at: string; source: string; text: string };       // vehicle feed batch ingested

type Cause =
  | { type: "citizen"; label: string; subject_id: string }           // "Citizen lodged SR-2026-001270"
  | { type: "vehicle_feed"; label: string }                          // "Vehicle feed: 183 detections"
  | { type: "clock"; label: string }                                 // "SLA timer: 75% of 120 h" / "Follow-up due"
  | { type: "agent"; label: string; run_id: number; agent: string }  // "Road Hazard Sensing created SR-…"
  | { type: "human"; label: string }                                 // "Crew W12-A marked WO-… completed"
  | { type: "weather"; label: string };                              // "Heavy rain warning + 25 reports"
```

### Layout (government style, same tokens; no chat bubbles, no gradients)
- Top: one-line counters for the last hour: runs by agent, actions taken, human decisions, "nobody clicked" count
  (= runs whose cause is not `human`/`citizen`).
- Main: a vertical timeline (newest at top). Each agent run is a bordered panel:
  - header: agent name, status tag (RUNNING pulses), model or "Rule-based", time, subject link;
  - **"Started by:"** the cause, with an icon per type (citizen / vehicle / clock / agent / person / weather).
    `type: "agent"` links to that run's panel (scroll + highlight) → this is how hand-offs are shown;
  - the steps as a compact list, appearing one by one while RUNNING: lookups in grey, `action` steps in bold
    (e.g. "Created SR-…", "Sent for rework", "Escalated to L2"), `rule` steps marked "check";
  - decision line + confidence; guardrails (if any) in an amber box: "Guardrail: …";
  - human outcome when it happens: "Accepted by Suresh Kumar" / "Overridden: <reason>".
- `human` items: a thin row with a person icon ("Suresh Kumar accepted SR-…"). `citizen` / `feed` items: thin
  rows with their icon.
- Right rail (desktop) or bottom (phone): a small **chain view** for the selected run: walk `cause` back to the
  root (e.g. Vehicle feed → Road Hazard Sensing → Case Investigator → (human) accepted → Evidence Auditor).
- Filters: agent, "only autonomous" (cause not human/citizen), "only actions".
- Accessibility: `aria-live="polite"` region announcing new runs; everything keyboard reachable.

### Done when
With the rain scenario or the vehicle feed running, runs appear within 2 s, steps fill in while RUNNING, and the
chain view shows Vehicle feed → Sensing → Investigator for a vehicle-created complaint.
