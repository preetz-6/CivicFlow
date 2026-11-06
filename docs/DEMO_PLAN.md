# CivicFlow: 10-minute demo plan

One story, told by the agents: a citizen reports a pothole near a school, and five agents plus four people take it
from report to verified repair, while other agents work on their own in the background. The full reference script
with every click is `docs/DEMO_SCRIPT.md`; this is the version that fits in 10 minutes.

**The message to land:** "Things happen that nobody clicked, every agent shows its reasoning, and a human makes
every decision that affects a citizen."

---

## The day before / morning of

- **Don't use Gemini on demo day before the demo.** The free key allows about 20 requests a day, and the demo needs
  about 12–15. The quota resets at 1:30 pm IST, so if you present in the afternoon, rehearse in the morning.
- Gemini is used only where it shows: the citizen's pothole report and its duplicate (Case Investigator), the
  completion photo (Evidence Auditor) and Ask CivicFlow. Everything else runs on rules by design. If the quota runs
  out, every agent falls back to rules by itself, and the demo still works.
- `.env`: `AGENT_MODE=live`, `LLM_PROVIDER=gemini`, `LLM_AGENTS=investigator,auditor,ask`.

## 15 minutes before

```bash
docker compose up -d
.\scripts\cf.ps1 demo          # fresh data for TODAY 09:00, SLA clock PAUSED (Mac/Linux: make demo)
python scripts/ops.py clock    # must say PAUSED
```

The reset prints two case numbers; they are the same on every reset:
- **SR-2026-001249**: already late (for Ask CivicFlow in step 7).
- **SR-2026-001248**: crew W12-B's job that hits 75 % of its time about 6 minutes after you resume (step 5).

**Screen setup (three windows, all at http://localhost:5173):**

| Window | Browser | Logged in as | Used for |
|---|---|---|---|
| **A** | Normal window | nobody, then `field.w12a` / `Field@2026` | Citizen, then field crew |
| **B** | Private window | `officer.w12` / `Officer@2026` | Ward officer |
| **C** | Second browser (Edge) | `control` / `Control@2026` | Control Room; open **Agent Operations** |

Also open a tab with **http://localhost:5173/agents** (the flowchart; it follows the latest case live) and a
terminal in the project folder.

**Right before you start talking:**
```bash
python scripts/ops.py resume
```

---

## The 10 minutes

### 0:00 – 0:30 · The problem (talk, Window A home page)
"Corporations get thousands of complaints. Routing is manual, nobody chases stuck cases, citizens never hear back.
CivicFlow puts six AI agents on a normal government grievance portal." Point at **See how our AI agents work**.

### 0:30 – 2:00 · Citizen reports; the Case Investigator investigates (Window A, then /agents)
1. Top strip **ಕನ್ನಡ** → **ದೂರು ದಾಖಲಿಸಿ** (Lodge Grievance). Category **ರಸ್ತೆ ಗುಂಡಿ** (Pothole). Leave the pin where it is
   (the school, satellite view).
2. Description: `ಶಾಲೆಯ ಗೇಟಿನ ಮುಂದೆ ದೊಡ್ಡ ರಸ್ತೆ ಗುಂಡಿ, ಮಕ್ಕಳು ಸುತ್ತಿ ನಡೆಯಬೇಕಾಗಿದೆ. Big pothole at the school gate.` Mobile
   `9845000001`, tick both boxes, the sum, **ಸಲ್ಲಿಸಿ**.
3. The slip appears, and below it **"Our AI agent is checking your complaint"**: the lookups appear one by one
   (ward, school 55 m away, road class, nearby complaints, SLA), then **Checked and routed**.
   **Say:** "Nobody clicked anything. Within seconds an agent investigated it like a ward engineer would."
4. Switch to the **/agents** tab → click the **Case Investigator** box: started by, each lookup, why, safety rules,
   "AI model gemini-2.5-flash".

### 2:00 – 2:45 · A second citizen, different words: merged, with the reason (Window A, then B)
1. Window A: **Lodge Grievance** again (English), Pothole, pin unchanged. Description:
   `Deep hole on the road in front of the school, my scooter tyre burst there yesterday`, mobile `9845000002`, submit.
2. Window B (`officer.w12`) → **Complaint Queue** → open the new one. The box at the top:
   **Merged as a duplicate of SR-…** with **Why** (17 m away, minutes apart, only 29 % similar by wording) and
   **Agent's reading**. **Say:** "The wording rule alone wasn't sure. The agent read both reports and confirmed."
   *(If Gemini is unavailable it shows "Possible duplicate" in amber instead: click **Merge**. Same point.)*

### 2:45 – 3:45 · Connected vehicles find what nobody reported (terminal, Window C)
1. Terminal:
   ```bash
   docker compose run --rm simulator python sim.py --once
   ```
   It prints `accepted 185, rejected 4`, including **"personal data not accepted: vin"**.
2. Window C → **Road Hazard Map** (satellite): grey = speed breakers filtered, green = confirms the school pothole,
   red = **new complaints created from vehicle data**, purple = a repair that failed.
3. **/agents** tab, **Recent cases** → one of the new vehicle cases: **Vehicle feed → Road Hazard Sensing → Case
   Investigator**. **Say:** "One agent handed work to another. No human involved."

### 3:45 – 6:00 · Repair, a fake photo caught, approval (Windows B, A, C)
1. Window B: open the **school pothole** (the first one) → **Accept** → **Create work order** → crew **W12-A** →
   **Create and assign**.
2. Window A: **Staff Login** as `field.w12a` → **My Jobs** → the job → **Start job**.
3. Terminal: `python scripts/photos.py` → upload **`2_after_2km_away.jpg`** → **Mark completed**.
   Seconds later: **Rework**, "Photo location 2.1 km from complaint site (limit 50 m)".
   **Say:** "The crew tried to close it with a photo from somewhere else. The Evidence Auditor caught it."
4. **Restart job**, `python scripts/photos.py` again, upload **`1_after_at_site.jpg`**, **Mark completed** → PASS.
5. Window C → **Verification Queue**: before/after, every check → **Approve**.
   **Say:** "The agent can send work back on hard evidence. Only a human can sign it off."
   *(Optional if time allows: Window A, Track Grievance with the number and mobile, progress bar at Resolved,
   5 stars, Confirm.)*

### 6:00 – 7:00 · The Follow-up agent steps in on its own (Window B)
By now SR-2026-001248 has reached 75 % of its time (a pop-up notice appears on the staff screens). If not:
`python scripts/ops.py advance 6`.
- Window B → **Complaint Queue** → **Pending Reassignment Proposals**: "crew W12-B has 6 jobs for 4 slots;
  cold-mix bitumen out of stock; propose crew W13-B, free, 1.2 km away." **Approve**.
  **Say:** "A timer woke the agent. It worked out *why* the case is late and proposed a fix. The officer approves."

### 7:00 – 8:00 · Heavy rain: 25 reports become 2 incidents (terminal, Window C)
```bash
docker compose run --rm simulator python sim.py --scenario rain --seed 3
```
Window C → **Incidents**: **Kengeri Underpass Waterlogging** and **RR Nagar Arch Drain Overflow**, situation
summary, English + Kannada advisory → **Publish advisory**. Window A home page: it scrolls in **What's New**.

### 8:00 – 9:15 · Ask CivicFlow (Window C)
1. **Ask CivicFlow** → type `Why is SR-2026-001249 late?` → crew W12-B overloaded, work not started, LED driver
   out of stock. Open **how it found this**: the lookups the agent chose.
2. **Let a judge ask one.** Good ones: "Which ward needs the most attention?", "How many potholes did vehicles find
   that no citizen reported?", "What does the charter say about reopening?"

### 9:15 – 10:00 · Close (Window C)
**Agent Operations**: every run of the last ten minutes with **Started by**: citizen, vehicle feed, SLA timer,
another agent. **Say:** "Half of these, nobody clicked. Every one shows its reasoning, and every decision about a
citizen was a person's." Dashboard: hover a pin on the satellite map (status, time left, the agent's decision).

---

## If something goes wrong

| Problem | Do this |
|---|---|
| Answers say "Rule-based" | Gemini quota is used up or unreachable. Keep going: the flow is identical. Say "with the model offline it falls back to rules". |
| The second pothole shows "Possible duplicate" | Click **Merge** in Window B and show the reason box. |
| No reassignment proposal at 6:00 | `python scripts/ops.py advance 6` |
| No incidents after rain | Wait 20 s, or `python scripts/ops.py run surge` |
| A page says "Page not found" | `docker compose restart web` |
| Everything shows as breached | The clock ran too long: `.\scripts\cf.ps1 demo`, then `python scripts/ops.py resume` |

## Not in the 10 minutes (keep for questions)
- Streetlight at the Kengeri bus stand: repeat failure, BESCOM referral, follow-ups, L2 escalation
  (`docs/DEMO_SCRIPT.md` step 4).
- Accessibility: A-/A/A+, high contrast, screen reader access, everything in Kannada.
- The six agents and their tools: `docs/AGENTS.md`.
