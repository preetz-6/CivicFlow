# CivicFlow: Demo Script (about 10 minutes)

Follows the demo story in `docs/BRIEF.md` §11. Every step uses real screens and the real API; the external parts (vehicle feed, SMS gateway, BESCOM/BWSSB, weather) are simulated behind adapters; see the README.

## Before you start

1. **Reset the data (any time before the presentation).**
   ```bash
   docker compose up -d --build
   make demo            # Windows without make: scripts\cf.ps1 demo
   ```
   This reseeds the city and **pauses the SLA clock** at 09:00. The clock runs 60x real time (1 real minute = 1 SLA hour), so without the pause every case would be breached an hour later. Check with `python scripts/ops.py clock` (it says `PAUSED`).
2. **When you start presenting:** `python scripts/ops.py resume`. Pause again any time with `python scripts/ops.py pause`.
3. If ports 5433 / 8000 / 5173 are taken, set `DB_PORT`, `API_PORT`, `WEB_PORT` in `.env`.
4. Agents: `AGENT_MODE=replay` replays the recorded model answers and falls back to rules on a miss; `AGENT_MODE=live` uses the model (Gemini free tier: few requests per day). With no key everything still works on rules and says "Rule-based".
5. Open http://localhost:5173 in **two browser windows** (one normal, one private) so a citizen and a staff user can be on screen at once. Put **http://localhost:5173/agents** in a third tab: it follows the latest case live.
6. Exact inputs that match the recordings (also in `backend/app/seed/demo_story.py`): pothole description `ಶಾಲೆಯ ಗೇಟಿನ ಮುಂದೆ ದೊಡ್ಡ ರಸ್ತೆ ಗುಂಡಿ, ಮಕ್ಕಳು ಸುತ್ತಿ ನಡೆಯಬೇಕಾಗಿದೆ. Big pothole at the school gate.` (mobile `9845000001`), then `Huge pothole near the school gate, kids at risk` (`9845000002`) and `Pothole at the school gate, two wheelers falling` (`9845000003`); streetlight `Streetlight not working at Kengeri bus stand, very dark at night, women feel unsafe` (`9845000002`); simulator `--seed 7` and `--scenario rain --seed 3`. Anything else still works, on rule-based analysis.

| User ID | Password | Role | Used in steps |
|---|---|---|---|
| `officer.w12` | `Officer@2026` | Ward Officer, Ward 12 Kengeri | 2, 4, 5, 6 |
| `field.w12a` | `Field@2026` | Field crew W12-A | 5 |
| `control` | `Control@2026` | Control Room / Commissioner | 3, 4, 5, 7, 8, 9 |

Citizens never log in: they **Lodge Grievance** and **Track Grievance** with the Grievance No. and the tracking code or mobile number.

Keep a terminal open in the repo root for the simulator, the clock (`python scripts/ops.py ...`) and the photo tool (`python scripts/photos.py`).

---

## 1. A citizen reports a pothole (Kannada), 1.5 min

- Window A, home page: the hero banner, the **Live now** card (AI agent actions in the last hour) and the **See how our AI agents work** button. Top strip: click **ಕನ್ನಡ**; point out A-/A/A+ and high contrast.
- **ದೂರು ದಾಖಲಿಸಿ** (Lodge Grievance). The pin is already at the school pothole (12.9099, 77.4855). Category **ರಸ್ತೆ ಗುಂಡಿ**, the description, a photo (its GPS and time are kept), mobile number, tick both boxes, answer the sum, **ಸಲ್ಲಿಸಿ**.
- The acknowledgement slip appears, and below it **"Our AI agent is checking your complaint"**: the Case Investigator's lookups appear one by one (ward, school 55 m away, road class, nearby complaints, SLA policy), ending with **Checked and routed** and the decision. **Say:** "Within seconds of submitting, an agent has investigated and routed it; nobody clicked anything."
- Switch to the **/agents** tab: the same case as a chain of boxes. Click the Case Investigator box: started by, each lookup, why, any safety rule applied, result.

## 2. Officer reviews; two more reports merge, 1 min

- Window B: **Staff Login** as `officer.w12` → **Complaint Queue** → open the complaint. **System Analysis**: P2 (school, Mysore Road), routed to Roads, Ward 12. **Steps taken** shows every tool call.
- Window A: lodge the same pothole twice more with the other two descriptions and mobiles.
- Refresh the officer's case: reporter count **3**; the two new ones were auto-merged (Status History; each citizen's Track timeline says so).

## 3. Connected vehicles confirm it and find one nobody reported, 1 min

- Terminal:
  ```bash
  docker compose run --rm simulator python sim.py --once
  ```
  It prints `accepted 183, rejected 4` and the rejection reasons (outside the city, in the future, too old, contains a VIN): the ingestion API refuses personal data.
- Window B: `control` → **Road Hazard Map** (satellite view; Map / Satellite switch top right). Grey dashed = filtered (speed breakers, rail crossing); green = confirms a citizen complaint ("Confirmed by 7 connected vehicles"); red on Mysore Road = **new complaint created from vehicle data**; purple = possible repair failure. **Data Sources**: accepted / rejected and why.
- **/agents** tab: the Mysore Road case shows the hand-off **Vehicle feed → Road Hazard Sensing → Case Investigator**.

## 4. Streetlight: repeat failure, BESCOM referral, follow-ups, escalation, 1.5 min

- Window A: lodge **Streetlight Not Working**; drag the pin to the Kengeri bus stand (12.9079, 77.4828).
- Window B (`officer.w12`): System Analysis **"repeat failure; refer BESCOM"** (pole failed twice in 60 days, BESCOM feeder F-KGR-07, P2 because of the bus stand). **Accept**: the referral goes to BESCOM.
- Terminal: `python scripts/ops.py advance 24` twice. **Say:** "No reply from BESCOM, so the Follow-up agent chased them twice, then escalated to L2 with a written reason." Staff screens show a pop-up notice each time an agent finishes something.
- Control Room → Dashboard → **Escalations**; **Agency Liaison**: record BESCOM's reply (*Work in progress*, "Feeder fault found, repair tomorrow 11 am"). The citizen's Track page shows the honest reason.

## 5. Work order, fake completion photo caught, rework, approval, 2 min

- Window B (`officer.w12`): school pothole → **Create work order** → crew **W12-A** → **Create and assign**.
- Window A: **Staff Login** as `field.w12a` (phone-sized: browser device toolbar). **My Jobs** → the job → **Start job**.
- Terminal: `python scripts/photos.py` (stamped photos for the newest open job in `photos/<work order>/`). Upload `2_after_2km_away.jpg` → **Mark completed**.
- Seconds later the job is back as **Rework**: "Photo location 2.1 km from complaint site (limit 50 m)."
- **Restart job**, run `python scripts/photos.py` again, upload `1_after_at_site.jpg`, **Mark completed**.
- Window B (`control`) → **Verification Queue**: before / after side by side, every check, PASS → **Approve**. **Say:** "The agent can send work back on hard evidence, but only a human can verify it."
- Window A: **Track Grievance** with the number and mobile: the progress bar shows **Resolved**; before / after photos. **5 stars** → **Confirm Resolution** → **Closed**.

## 6. Follow-up agent: overloaded crew, no stock, honest delay, 1 min

- About 6 minutes after `resume`, the seeded streetlight job on crew W12-B reaches 75 % of its SLA (or `python scripts/ops.py advance 6`).
- Window B (`officer.w12`) → **Pending Reassignment Proposals**: crew W12-B over capacity, material out of stock; proposal crew W13-B, free, about 1.2 km away. **Approve**. The citizen's Track timeline says why it is late.

## 7. Rain: 25 reports become 2 incidents and a public advisory, 1 min

- Terminal: `make rain` (or `docker compose run --rm simulator python sim.py --scenario rain`).
- `control` → **Incidents**: **Kengeri Underpass Waterlogging — 17 reports**, **RR Nagar Arch Drain Overflow — 8 reports**, crew suggestion, the Commissioner's situation summary. **Publish advisory** (English and Kannada).
- Window A, home page: the advisory scrolls in **What's New** with a red NEW label.

## 8. Ask CivicFlow, 1 min

- `control` → **Ask CivicFlow**. Click the examples or type your own (let a judge ask one):
  - "Why is SR-… late?" (use the W12-B streetlight from step 6): overloaded crew, not started, LED driver out of stock.
  - "Which ward is worst this week and why?"
  - "How many potholes did vehicles find that no citizen reported?"
  - "What does the charter say about reopening a grievance?" (answer quoted from the Charter, source shown)
- Open **how it found this**: each lookup the agent chose. **Say:** "Same tools as the other agents, over the live data; every number links back to a case."

## 9. Close on the numbers, 30 s

- Control Room → **Dashboard**: the satellite live map (hover a pin: photo, status, time left, the agent's decision; click: **How the agents handled it**), total reports vs unique issues, within-SLA %, reopen rate.
- **Agent Operations**: every run of the demo with what started it ("Started by: SLA timer", "Road Hazard Sensing created SR-…") and the runs nobody clicked.

---

## If something goes wrong

| Problem | Fix |
|---|---|
| Every case shows as breached | The clock ran while you were away: `make demo` again (it pauses the clock), then `python scripts/ops.py resume` when you start. |
| System Analysis says "not available yet" | Refresh after a few seconds; agents run in the background. |
| The model is unavailable or out of quota | Agents fall back to rules on their own ("Rule-based"); the flow is the same. |
| The W12-B job has not reached 75 % yet | `python scripts/ops.py advance 6` |
| Incidents did not appear | `python scripts/ops.py run surge`, or wait 20 s. |
| A new page shows "Page not found" after `git pull` | `docker compose restart web` (Windows file watching). |
| Start again from a clean state | `make demo`, then `python simulator/sim.py --clear-weather`. |
