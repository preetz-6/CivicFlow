# CivicFlow: Demo Script (about 8 minutes)

Follows the demo story in `docs/BRIEF.md` §11. Every step uses real screens and the real API; the external parts (vehicle feed, SMS gateway, BESCOM/BWSSB, weather) are simulated behind adapters; see the README.

## Before you start (10 minutes before)

1. Start everything and load a fresh demo seed:
   ```bash
   docker compose up -d --build
   make demo            # Windows without make: scripts\cf.ps1 demo
   ```
   If ports 5433 / 8000 / 5173 are taken on the demo laptop, set `DB_PORT`, `API_PORT`, `WEB_PORT` in `.env` and, for a local `npm run dev`, `VITE_API_TARGET` in `web/.env.local`.
2. For a fast, network-independent run use the recorded agent answers: `AGENT_MODE=replay` in `.env` (falls back to rules on a cache miss). With no API key at all, every agent still works on rules and says "Rule-based analysis".
3. Open http://localhost:5173 in **two browser windows** (or one normal + one private window), so the citizen and the staff user are logged in at the same time.
4. Logins: **Login** → User ID + password. Passwords: citizens `Citizen@2026`, officers `Officer@2026`, field teams `Field@2026`, Control Room `Control@2026`. Nothing about the demo is shown on screen; keep this script (or the user list) beside you.
5. Replay only matches the **recorded** story, so use these exact inputs (they are also in `backend/app/seed/demo_story.py`): citizen1's pothole description `ಶಾಲೆಯ ಗೇಟಿನ ಮುಂದೆ ದೊಡ್ಡ ರಸ್ತೆ ಗುಂಡಿ, ಮಕ್ಕಳು ಸುತ್ತಿ ನಡೆಯಬೇಕಾಗಿದೆ. Big pothole at the school gate.` (mobile `9845000001`), then `Huge pothole near the school gate, kids at risk` (`9845000002`) and `Pothole at the school gate, two wheelers falling` (`9845000003`); streetlight `Streetlight not working at Kengeri bus stand, very dark at night, women feel unsafe` (`9845000002`); simulator `--seed 7` and `--scenario rain --seed 3`. Anything else still works, on rule-based analysis.

| User ID | Role | Used for |
|---|---|---|
| `citizen1` | Citizen (Kannada) | Steps 1, 5 |
| `officer.w12` | Ward Officer, Ward 12 Kengeri | Steps 2, 4, 5, 6 |
| `field.w12a` | Field Team, crew W12-A | Step 5 |
| `control` | Control Room / Executive Engineer | Steps 3, 4, 5, 7, 8 |

Keep a terminal open in the repo root for the simulator, the clock (`python scripts/ops.py ...`) and the photo tool (`python scripts/photos.py`).

---

## 1. A citizen reports a pothole (Kannada UI), 1 min

- Window A, top strip: click **ಕನ್ನಡ**. Point out the government portal frame: A-/A/A+, high contrast, prototype banner, "What's New" ticker.
- Menu **ದೂರು ದಾಖಲಿಸಿ** (Lodge Grievance). The map pin is already at the school pothole (12.9099, 77.4855).
- Category **ರಸ್ತೆ ಗುಂಡಿ** (Pothole), a description, a photo (upload the original file: its GPS and time are kept), mobile number, tick both boxes, answer the sum, **ಸಲ್ಲಿಸಿ**.
- **Say:** "The citizen gets an acknowledgement slip at once: grievance number, tracking code, ward, department and expected date." Click **ಮುದ್ರಿಸಿ** (Print) to show the slip prints cleanly.

## 2. The Case Investigator investigates; two more reports merge, 1 min

- Window B: log in as `officer.w12` → the complaint is at the top of **Complaint Queue** with its System Suggestion. Open it.
- **System Analysis** panel: P2 because it is 55 m from the Govt. school and on Mysore Road; routed to Roads, Ward 12. Expand **Steps taken**: every tool call (ward lookup, sensitive places, nearby complaints, asset history...) with its input and result.
- Window A: lodge the same pothole twice more (as `citizen2`, `citizen3`, or anonymously with other mobile numbers).
- Refresh the officer's case: reporter count **3**; the two new ones were auto-merged (the merge is visible in the Status History and in each citizen's Track timeline: "System linked your complaint with a similar report").

## 3. Connected vehicles confirm it and find one nobody reported, 1 min

- Terminal:
  ```bash
  docker compose run --rm simulator python sim.py --once
  # without Docker: python simulator/sim.py --once --api http://localhost:8000
  ```
  It prints `accepted 183, rejected 4` and the 4 rejection reasons (outside the city, in the future, 40 days old, contains a VIN): the ingestion API refuses personal data.
- Window B: log in as `control` → **Road Hazard Map**. **Say:** "Vehicle makers don't publish this data; this feed follows the partner API contract we designed."
  - Grey dashed circles = **filtered** (5 speed breakers and the railway crossing: hover them).
  - Green = confirms a citizen complaint. Open the school pothole: "Confirmed by 7 connected vehicles".
  - Red on Mysore Road = **new complaint created from vehicle data**; no citizen reported it.
  - Purple = possible repair failure (a spot repaired 10 days ago is being hit again; the crew is flagged for audit).
  - Scroll to **Data Sources**: accepted / rejected counts and the dead-letter reasons.

## 4. Streetlight: repeat failure, BESCOM referral, follow-ups, escalation, 1.5 min

- Window A (citizen): lodge **Streetlight Not Working**; drag the pin to the Kengeri bus stand (12.9079, 77.4828).
- Window B (`officer.w12`): open it. System Analysis: **"repeat failure; refer BESCOM"**: pole `STREETLIGHT-W12-00871` failed twice in 60 days, 3 lights out on the stretch, BESCOM feeder F-KGR-07, P2 because of the bus stand. Click **Accept**: the referral goes to BESCOM.
- Terminal: `python scripts/ops.py advance 24` twice (two unanswered follow-ups, then L2). Refresh the Control Room **Dashboard**. **Say:** "No reply from BESCOM, so the Follow-up agent chased them twice, then escalated to L2 with a written reason."
- Dashboard → **Escalations**: "...followed up 2 times with no response. Not municipal inaction." **Steps taken** opens the agent run.
- **Agency Liaison**: the referral and both follow-ups. Record BESCOM's response: *Work in progress*, "Feeder fault found, repair tomorrow 11 am". The citizen's Track page shows the honest reason for the delay.

## 5. Work order, fake completion photo caught, rework, approval, 2 min

- Window B (`officer.w12`): open the school pothole → **Create work order** → crew **W12-A** → scope → **Create and assign**.
- Window A: log out, log in as `field.w12a` (phone-sized screen: use the browser's device toolbar). **My Jobs** → the job → **Start job**.
- Terminal: `python scripts/photos.py` (writes stamped photos for the newest open job to `photos/<work order>/`). **Upload after photo** → `2_after_2km_away.jpg` → **Mark completed**.
- In a few seconds the job comes back as **Rework**: "Auto-check failed: Photo location 2.1 km from complaint site (limit 50 m)."
- **Restart job**, run `python scripts/photos.py` again (fresh timestamps), upload `1_after_at_site.jpg`, **Mark completed** → auto-check result.
- Window B (`control`) → **Verification Queue**: before / after photos side by side, each check (time, location, not reused, vision), verdict PASS. **Approve**. **Say:** "The agent can send work back on hard evidence, but only a human can verify it."
- Window A: log in as `citizen1` (or use **Track Grievance** with the number and mobile): status **Resolved**, before / after photos. Choose **5 stars** → **Confirm Resolution** → **Closed**.

## 6. Follow-up agent: overloaded crew, no stock, honest delay, 1 min

- The seeded streetlight job on crew W12-B reaches 75 % of its SLA about 6 minutes after `make demo` (or `python scripts/ops.py advance 6`).
- Window B (`officer.w12`) → **Complaint Queue**: **Pending Reassignment Proposals** shows the Follow-up agent's diagnosis (crew W12-B over capacity, material out of stock) and its proposal: crew W13-B, free, about 1.2 km away. **Steps taken** shows how it worked that out. **Approve**.
- The citizen's Track timeline now says why it is late, in plain words.

## 7. Rain: 25 reports become 2 incidents and a public advisory, 1 min

- Terminal:
  ```bash
  make rain            # or: docker compose run --rm simulator python sim.py --scenario rain
  ```
- Window B (`control`) → **Incidents**: weather alert, **Kengeri Underpass Waterlogging — 17 reports** and **RR Nagar Arch Drain Overflow — 8 reports**, crew suggestion as text, the Commissioner's situation summary.
- Edit the advisory if you like (English and Kannada) → **Publish advisory**.
- Window A: home page: the advisory scrolls in **What's New** with a red NEW label (in Kannada when ಕನ್ನಡ is selected).

## 8. Close on the numbers, 30 s

- Control Room → **Dashboard**: total reports vs unique issues (duplicates and incidents collapse them), citizen-confirmed vs automatic closures counted separately, within-SLA %, reopen rate.
- **Agent Activity Log**: every agent decision of the demo, which ones were rule-based, which ones an officer accepted or overrode; open any row for the full tool trace.

---

## If something goes wrong

| Problem | Fix |
|---|---|
| System Analysis says "not available yet" | Click **Refresh** on the case after a few seconds; agents run in the background. |
| A step needs the model and the network is down | It falls back to rules on its own ("Rule-based analysis"); the flow is the same. |
| The W12-B job has not reached 75 % yet | `python scripts/ops.py advance 6` |
| Incidents did not appear | `python simulator/sim.py --scenario rain` triggers the Surge Commander directly; or wait 20 s. |
| Start again from a clean state | `make demo`, then `python simulator/sim.py --clear-weather`. |
| Backup | The recorded demo video (see README). |
