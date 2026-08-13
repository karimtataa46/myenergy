# myEnergy — Documentation

> **Living documentation.** We append a section here each time we complete a piece of work.
> Master plan lives in **Notion**; individual tasks are tracked as **GitHub Issues**; this
> file is the source-of-truth record of what is built and how it works.

_Last updated: 2026-08-13_

---

## Vision

myEnergy is a **predictive Energy Management System (EMS)**. Its defining capability is
**forward-looking decisions from an accurate, multi-hour forecast**: it never buys grid energy
it could get cheaper or free soon.

**Flagship behaviour — "wait for the sun":**

> Battery at ~45% at 13:00, cloudy now, but the forecast shows strong solar within ~1 hour.
> The EMS does **not** grid-charge now — it bridges the short gap minimally and charges from
> free solar once it arrives.

---

## North-Star acceptance test

The core feature is "done" when a test proves this:

- **Scenario:** 13:00, battery ~45%, low solar now (cloudy), forecast shows strong solar within ~1 hour.
- **Pass =** the EMS does not grid-charge now; it bridges the short gap minimally and charges from solar once it arrives.
- **Measured:** over a simulated cloudy day, grid kWh bought is lower than today's greedy brain, **and** the battery never hits critical (reliability preserved).

---

## How we work

- **One issue at a time** (tracked as GitHub Issues). Each issue has a goal, a definition of done, and a test.
- Before building: agree the *why* and approach. After building: it must be **green and understood** before it's merged or deployed.
- When an issue is done, add an entry to the **Completed work log** below.

---

## Roadmap (milestones)

| Milestone | Goal |
|---|---|
| **M1 — Predictive foundation** | Understand the current decision baseline; give the EMS an accurate, longer forecast to decide on. |
| **M2 — Wait-for-sun** | The predictive battery decision. Pass the North-Star test. |
| **M3 — Co-optimised loads** | Fold the flexible devices into the same optimisation; retire the greedy device rules. |
| **M4+** | Features chosen next (spot pricing, more devices, degradation-aware, …). |

---

## System map (current state)

Three surfaces currently share one codebase:

1. **`/estimate` → `/facility`** — a user enters their site (city, solar, battery, usage), sees projected savings, then a live per-session dashboard of *their* facility. Runs the **LP optimizer** (`simulation/optimizer.py`) over real weather.
2. **`/` (demo dashboard)** — one hard-coded factory where the **greedy rule brain** (`backend/brain.py`) controls the battery + flexible devices in real time, polled every 5s.
3. **`/sim` + test suites** — proves the optimizer is provably optimal; a real-time accelerated savings race.

> The full "how it decides today" write-up is **Issue M1.1**.

---

## Completed work log

_Entries are appended here as each issue is finished._

- **2026-08-13 — Project reset to a planned, milestone-driven process.** Defined the predictive-EMS vision, the North-Star acceptance test, and the M1–M3 roadmap. Set up GitHub Issues + this living doc.
