# Progress Tracker

Update this file whenever the current phase, active work, or implementation state changes.

## Current Phase

- The prototype is feature-complete for its current scope, on a **simulated** plant (Munich, 250 kWp solar, 200 kWh / 50 kW battery, about 90 kW daytime load). There is no real hardware and there are no measured savings. The owner builds it as a learning and CV prototype.
- On 2026-10-18 the README was corrected for honesty (not committed yet) and the context files were created (`context/` is untracked). `main` is at `eea63ab` (2026-10-08, merge of PR #40). Nothing was committed after that. One pull request is open and not merged: #38 (see In Progress).

Checked on 2026-10-18 (all run today, local `.venv` is Python 3.9.6):

- Tests: `.venv/bin/python -m pytest -m "not e2e"` gave **268 passed** in 3.29 s. 276 tests are collected. The 8 browser tests were **not run**.
- Standalone proofs, run from `simulation/`: `verify_simulation.py` 39 passed, 0 failed. `test_decisions.py` 12 passed, 0 failed.
- Savings: `savings.layers(30)` gave solar 7,113.12; battery on a timer 1,080.50; myEnergy 40.95 (111.13 with a perfect forecast); bill without anything 12,668.40; bill 4,433.83. All EUR, all simulated.
- CI: the last run on `main` succeeded on 2026-10-08 (`gh run list`). I did not trigger CI today.
- Coverage: the CI gate is 40%. `code-standards.md` records 66% measured on 2026-10-18. I did not measure it myself.

## Current Goal

None active. No work is running in this session. Only one branch holds work that is not in `main`: `m6-p3-honest-savings` (PR #38, one commit, 2026-10-08). The old local branch `feature/facility-config` shows 4 commits, but `git cherry` says all four are already in `main` under other hashes.

Proposed next unit, **proposed, not yet agreed by the owner**: Next Up step 1 (solar calibration and the one-hour shift in `weather.py`). Before that, the owner should decide what happens to PR #38 (Open Question 6), because it changes the savings code and the numbers that the context files and the README quote.

## Completed

Newest first. Dates are commit dates from `git log`. "Per commit message" means the only evidence is what the commit says. "Ran today" means I ran it on 2026-10-18.

- **README honesty correction and context files (2026-10-18, not committed)**: the README was rewritten where it overstated, and the context files were written from the code.
  - README changes (`git diff` shows 66 lines added, 26 removed):
    - The first sentence now says the factory is **simulated**. The old text said myEnergy "reads a facility's solar inverter, battery and grid meter", which implied real hardware.
    - The savings table is labelled as one **simulated** month. It says the month is summer-like (seeded weather, one cloud value per day) and that a full year would save clearly less.
    - The forecast error is explained: each day's cloud cover is shifted by a random amount (standard deviation 0.15).
    - The EUR 270 a month figure now states its conditions: simulated prices, the default 100 kWp factory, a perfect forecast. It is called an upper bound.
    - The test count is now "276 pytest tests (268, plus 8 browser tests)". The old text said "298 automated checks".
    - The code map lists the real modules (`energy_manager.py`, `planner.py`, `prices.py`, `assistant.py`) and names the four dormant developer modules.
    - The evaluation line says the first real run graded only 7 answers, found two defects, and a full re-run is pending.
    - New "Known limitations" section (simulated plant, two solar models, solar read one hour late, coarse savings simulation, cost-only objective). New text on the safety rules and on "cost, not grid energy". The status line now says "learning prototype". The tech stack names DWD, Energy-Charts and Chart.js.
  - Context files created: `project-overview.md`, `architecture-context.md`, `ui-context.md`, `code-standards.md`, `ai-workflow-rules.md`, and this file. `context/AGENTS.md` and `context/CLAUDE.md` existed before (file dates 2026-10-16 and 2026-10-15) and are wrong (see Small fixes S17).
  - Verified: I read the README diff and the six context files. The numbers I could re-run today match the README: 268 + 8 = 276 tests, savings 40.95 and 111.13 (README says "about EUR 40" and "EUR 110"). I counted 20 cases in `automation/evals/cases.json`, as the README says.
  - Not exercised: the browser tests. The README's EUR 270 figure: I did not re-run `demo_dynamic_pricing.py`. `project-overview.md` says it gave EUR 266 on 2026-10-18. I did not check every other README sentence against the code.

- **Real weather only (#39, PR #40, 2026-10-08)**: a defect found on the Render deployment. Open-Meteo could not be reached, `weather.fetch_forecast` silently returned a clear-sky forecast, and the page said "Running normally" while the plan waited for sun that was not coming.
  - `weather.fetch_real_forecast`: Open-Meteo first, then the German weather service (DWD) through Bright Sky. If both fail it raises `ForecastUnavailable` and never invents weather.
  - The live plant keeps its last real forecast. With none, it runs on the safe rules and says so. `/api/plan` names the weather source and any refresh error. The page shows both.
  - Tests: the refresh tests run in their own thread; a new autouse guard `no_internet` in `tests/conftest.py` makes any test that reaches the internet fail at once.
  - Verified: per commit message, and by `gh run list`: CI failed on the first push of the branch (2026-10-08 09:38) and passed after the test fix `7e48473`. The `main` run after the merge passed. Ran today: the weather tests are part of the 268.
  - Not exercised: `docs/BUGS.md` has **no row for #39** (Small fixes S4). I did not check the Render deployment. Bright Sky's timestamp meaning is not verified. The developer estimate APIs still fall back to a synthetic forecast on purpose.

- **Real prices and hourly decisions, M6 steps 1 and 2 (#31 PR #36, #32 PR #37, 2026-10-06 to 2026-10-08)**: the plant now plans and decides with real German day-ahead prices.
  - Step 1 (`e8b3732`): `backend/prices.py` reads Energy-Charts (zone DE-LU), averages 15-minute prices into hours, adds EUR 0.10/kWh for fees and taxes, and pays export at the market price minus EUR 0.01. Hours not yet published are copied from a day earlier and flagged. Offline it falls back to a simulated price model and says so. New `GET /api/prices`.
  - Step 2 (`8fe16cf`): the planner carries the buy and sell price of every hour. "Cheap" and "dear" are the cheapest and dearest third of the next 24 hours. The plan summary names every buying window. `/api/site` describes the dynamic tariff. The page, the agent's tool descriptions and one eval case follow.
  - Flaky test fix `1c7bdf8` (2026-10-06): plan labels repeat within 36 hours, so a lookup by label found tomorrow's value.
  - Verified: per commit message: acceptance tests in `tests/test_dynamic_prices.py` ("buys 55 instead of 158 kWh before a sunny day"). Ran today: they pass in the 268. The PR #38 text shows the real price feed was used on 2026-10-08.
  - Not exercised: I did not call the price API today. The EUR 0.10 surcharge is an assumption (`prices.py`). Issues #34 (price curve and cheapest hours in the interface) and #35 (agent, briefing and eval follow the prices) are **still open**. The page has the cheap-hour bands, the price now and the cheapest hour, but does not draw a price curve (`hours[].price` is unused). I did not compare the two issues with the code line by line.

- **Honest savings and redesign (PR #30, 2026-10-06)**: the savings figure was corrected and the page was redesigned.
  - The bill is split into layers: solar panels, battery on a simple timer, myEnergy's planning. Only the last layer is credited to the software. The software is judged with a forecast about 15% off (`factory.forecast_of`).
  - The old README claim of about EUR 740 a month was removed. It credited the night tariff and a perfect forecast to the software.
  - The page got an animated energy-flow diagram, a sticky section menu, numbers that glide, and reduced-motion support.
  - Verified: per commit message: "about EUR 41 a month". Ran today: `savings.layers(30)` gives 40.95, and `tests/test_savings.py` passes in the 268.
  - Not exercised: the figure is one simulated summer-like month on a fixed day/night tariff. The live plan uses hourly prices since M6, so the two now describe different tariffs. A full year would save less (README).

- **AI agents, M5 (#23 to #29, PR #27, 2026-10-04)**: an AI assistant on top of the API. It is not part of the control path.
  - Docker Compose runs myEnergy and n8n together (#23). n8n is bound to `127.0.0.1`.
  - Chat agent "Frag deine Anlage" (#24) with four read-only tools. Daily German briefing (#25). Evaluation set and runner (#26). Tests for the workflows and the grader.
  - "Ask your plant" in the page: `POST /api/ask` goes through `backend/assistant.py` to n8n. 5 questions a minute per visitor, 500 characters each. The model was changed from Claude to Google Gemini (free tier) in `147a0aa`.
  - Verified: per commit message: browser to myEnergy to n8n to Gemini "checked live, desktop and phone". The first real eval run (`automation/evals/results/20261004-122353/summary.md`, read today) graded 7 answers: 4 passed; 12 trials got no answer because the free daily quota ran out. It found #28 (English questions answered in German) and #29 (the agent called the plant "155 kWp"); both are fixed. The grader is tested with good and bad answers and was mutation-checked (per commit message). Ran today: `test_workflows.py`, `test_assistant.py` and `test_eval_grading.py` pass in the 268.
  - Not exercised: **a clean full eval re-run does not exist**. The fixes for #28 and #29 were never graded (`docs/BUGS.md`: "re-run pending"). One graded answer also failed the `number` check (`live-grid-en`) and has no row in `BUGS.md`. The daily briefing: `automation/briefings/` holds only `.gitkeep`, so there is no file in this checkout showing that a briefing was written. The Claude model path is documented but no Claude node is in the workflows. Issues #24, #25, #26, #28 and #29 are still open on GitHub.

- **Single operator interface (#21, 2026-09-27)**: five pages (`/`, `/estimate`, `/facility`, `/sim`, `/plan`) became one page at `/`, for the person who operates the plant.
  - Sections: Right now, Tonight and tomorrow, Savings, Your system. A status pill. New `GET /api/site`.
  - The old pages were removed and return 404. Their developer APIs and modules stay (the "dormant" subsystems, see Open Question 4).
  - Defect #22 (the "right now" sentence contradicted the power flow) was fixed the same day (`bfc7d2f`).
  - Verified: per commit message: browser tests for each section, a pixel check that the chart really draws (mutation-tested), and the no-forecast and unreachable-plant states. `ui-context.md` records a headless Chromium check at 4 widths on 2026-10-18.
  - Not exercised: the 8 browser tests were not run today. Known gaps are listed in `ui-context.md` (Accessibility, Known UI Facts) and in Small fixes S5 to S12.

- **"Wait for the sun" (#2, #12 to #19, 2026-09-26)**: the live decision now plans from the full hourly forecast. This is the core idea of the product.
  - `#12` fix: a battery at or below 15% was never recharged. `#13`: acceptance tests written first, marked `xfail(strict=True)`. `#14`: `planner.py` plans 36 hours with the LP, `energy_manager.py` joins planner and rules, `brain._follow_plan` is the safety envelope. This closed `#2`.
  - The demo plant was changed to 250 kWp (`44da836`), because the old 100 kWp plant never made more solar than its load and the feature could not show.
  - `/api/plan` and the `/plan` page (#16, #17). Fixes: #15 (plan-following bought peak grid power), #18 (tariff followed UTC, not Munich time), #19 (solver noise bought grid power).
  - Verified: per commit message: before a sunny day the demo plant buys 81 kWh overnight, before a cloudy day 158 kWh. 125 pytest tests passed at #14. Defects #15, #18 and #19 were found by live runs and each has a regression test (`docs/BUGS.md`). Ran today: `tests/test_acceptance.py` passes in the 268.
  - Not exercised: the plan was never tested against a **wrong** forecast in the live loop. The plant's solar comes from the same forecast the planner uses (architecture-context.md, Known Limitations 3). Issue #20 (the planner treats the current hour as a full hour) is open and is **not recorded in any context file**. The two solar models disagree and the sun is read one hour late (Next Up step 1).

- **Design audit (`1ef5c6f`, 2026-09-23)**: `docs/DESIGN.md` describes the structure at that time, five problems and a refactor backlog R1 to R4.
  - R1: make `backend/` and `simulation/` real packages and remove the `sys.path` edits. R2: one simulation instead of four. R3: one decision interface. R4: one shared dashboard script.
  - Verified: nothing to verify. The file says "draft for review".
  - Not exercised: **R1 to R4 were never done as written.** Today there are still 7 `sys.path` edits in `backend/` (architecture-context.md, System Boundaries). The page problem (P1, P5) disappeared when #21 removed four pages. `docs/DESIGN.md` is out of date (four pages, "two brains", 152 checks) and is history, not a plan.

- **Test pyramid T0 to T5 (#4 to #11, 2026-09-23)**: the project got its tests in one day.
  - T0 pytest set up (#4). T1 unit tests for the rules, models, engine, weather and pricing (#10, #5). T2 and T3 integration and API tests with the network mocked (#6, #7). T4 browser tests with Playwright (#8). T5 GitHub Actions CI with a coverage gate of 40% (#9).
  - `docs/BUGS.md` was started. Defects found by the tests: #10 (`urgency()` divided by zero), #11 (yearly and monthly savings did not add up).
  - Verified: per commit messages: pytest grew from 10 to 42, 65, 66, 68 and 101 tests during the day. Quoted coverage: `brain.py` 28% to 96%, `engine.py` 0% to 100%. Ran today: 268 pass.
  - Not exercised: the CI gate (40%) is far under the measured 66%. The two standalone proofs run in CI but **exit 0 even when a check fails**, so that CI step cannot fail (Small fixes S1). The first browser tests drove the `/estimate` page, which no longer exists; they were rewritten in #21.

- **Per-city estimate and facility pages, and the decision rules (2026-08-08 to 2026-08-16)**: a second product was built next to the first prototype.
  - Steps 1 to 6: the test plant moved to Munich. `FacilityConfig` lets the engine run any facility. `pricing_service.py` maps a city to a country tariff. `estimate_service.py` returns a savings estimate for a city. `facility_live.py` runs a per-user live session. City autocomplete.
  - Fixes: no-cache headers for pages; a frozen battery; identical results for every city; and `62190fc` (2026-08-10), which fixed the control loop crash and the empty `/api/live` (defects B-01 to B-06).
  - `3c05e18` (2026-08-11) added to `brain.py`: a 95 kW demand cap, an arbitrage gate (0.88 round trip, EUR 0.04/kWh wear), and minimum on and off times for devices.
  - On 2026-08-13 a `documentation.md` was added and removed the same day. Planning moved to Notion and GitHub issues (per commit message). The README was rewritten on 2026-08-16.
  - Verified: per commit messages: "all suites pass, savings unchanged" (`5efe49f`); "test_energy_logic.py 16/16, decisions 12/12, livesim 7/7" (`3c05e18`). Those three scripts are now legacy runners outside pytest.
  - Not exercised: the pages are gone. Their APIs and four modules (about 800 lines) are still served and shipped, and still tested. Issue #1 (document how it decides) and issue #3 (measure forecast accuracy) date from this time and are still open.

- **First prototype (2026-06-28 to 2026-06-30)**: the starting point.
  - FastAPI backend with a 5-second control loop, the validated simulation engine, the LP optimiser (SciPy), a dashboard and a live savings page (`/sim`). Procfile, `render.yaml`, tests, README.
  - Live solar from the real Open-Meteo forecast (`f6aa422`). `simulation/stress_test.py` (random scenarios and edge cases). Dockerfile and a Render deploy through Docker (`29567cb`).
  - Verified: per commit message: the container was "verified locally". Ran today: the two standalone proofs pass (39 and 12 checks).
  - Not exercised: the first dashboard and `/sim` no longer exist. The README link to the public demo was removed on 2026-08-16. I did not check whether the Render service still runs. I did not run `stress_test.py`.

## In Progress

No work is running in this session. One unit is open on GitHub and not merged:

- **PR #38, "M6 step 3: honest savings on real hourly prices" (closes #33), branch `m6-p3-honest-savings`**, one commit `af33ad9` (2026-10-08). CI on the branch passed (`gh`). It is based on `e87df45`, so it does not contain the #39 fix.
  - What it does (from the PR text and `git diff --stat`, 12 files, 302 lines added, 104 removed): `engine.simulate` takes hourly prices; a new `controllers.price_rule` replaces the timer as the savings baseline; `prices.daily_prices`; `savings.py` runs on the last 30 days of real prices; the page, two n8n workflows and the README change wording ("battery on a simple price rule", "Last 30 days" instead of "A full month").
  - Its numbers (PR text, simulated weather, not run by me): panels about EUR 6,023, price rule about EUR 957, myEnergy's planning about EUR 302 (4.7% of the bill). With a perfect forecast EUR 518; with a 30% error EUR 281. On the old fixed tariff the same comparison gives EUR 41.
  - It touches two areas that `ai-workflow-rules.md` protects: the honest baseline (`savings.py`, the timer) and `simulation/engine.py`.
  - Its README edits start from the old README. They will **conflict** with the uncommitted README correction of 2026-10-18, because both rewrite the same savings paragraph and the same test-count line. I did not try the merge.
  - Not decided by me. See Open Question 6.

## Next Up

**Proposed, not yet agreed by the owner.** The 7 steps keep the order of the handoff. One unit at a time, one branch and one PR per unit (`ai-workflow-rules.md`).

Before step 1: the owner decides PR #38 (Open Question 6). If it is merged, the README and the context files that quote savings need an update first (Open Questions (b), item 1).

1. **Fix the solar calibration and the one-hour shift in `weather.py`; one test for each.**
   - Why first: every "wait for the sun" decision depends on it. Size: small.
   - Depends on no open question. It changes decision behaviour, so it needs the owner's request or an agreed issue, and the four conditions in `ai-workflow-rules.md` ("Changes To Decision Behaviour"). Which solar model is wrong (1.0 x or 0.62 x of nameplate) and what factor to use must be agreed with the owner. The README says real plants are usually 0.75 to 0.85. If a `factory.py` constant changes, re-run `savings.layers(30)` and update the numbers in three files.
   - Open-Meteo documents radiation as the mean of the preceding hour (verified on its docs page, per `architecture-context.md`). Bright Sky's meaning is not verified.
2. **Decide the objective, then add a grid-kWh or CO2 weight, battery wear and a ready-by constraint to the LP.**
   - Why: makes the software do what the owner actually asked for. Size: medium.
   - **Blocked by Open Questions 1 and 2.** Do not start before the owner answers them. Do not add a grid-kWh or CO2 term until then (`ai-workflow-rules.md`).
3. **One `SiteConfig` (location, time zone, price zone, array, battery, reserve) read by every module.**
   - Why: removes the scattered constants before more are added (`code-standards.md`, Inconsistencies 10). Size: small.
   - No open question blocks it, but Open Question 3 (one plant or many) shapes its design. It is a refactor: keep it apart from any behaviour change.
4. **A `Plant` interface with `SimulatedPlant`; the control loop depends only on it; a fail-safe when readings stop.**
   - Why: the step between "prototype" and "can touch hardware". Size: medium.
   - Depends on Open Question 3 (hardware or simulator-only). A fail-safe is a new safety behaviour.
5. **A forecast-uncertainty margin; log forecast against actual solar.**
   - Why: makes "wait for the sun" safe and measurable. Size: medium. It is also issue #3.
   - Logging means storing more than 24 hours of data and probably a schema change. Both are the owner's call (`ai-workflow-rules.md`). Tell the owner before you start.
6. **Remove or isolate the dormant subsystems; make `backend` and `simulation` real packages; retire the `sys.path` edits; refresh `docs/DESIGN.md`.**
   - Why: less to maintain, fewer ways to break. Size: medium.
   - **Blocked by Open Question 4.** Deleting and packaging are different changes: split them. `import planner` or `import energy_manager` fails alone today (Session Notes).
7. **Put flexible loads and a learned load forecast into the optimiser.**
   - Why: the real endgame of the product. Size: large.
   - A learned forecast is machine learning, which `project-overview.md` lists as **out of scope**. This needs the owner to change the scope (Open Question 7).

### Small fixes

Each is one unit. None is started. "Where" is the file or the place that records it.

- **S1. CI proofs cannot fail.** `simulation/verify_simulation.py` and `simulation/test_decisions.py` exit 0 even when a check fails, so the last CI step always passes. Make them exit non-zero on a failed check. (Where: `.github/workflows/tests.yml`; `architecture-context.md`, Known Limitations 18.)
- **S2. The coverage gate is far below reality.** The gate is 40% and the value was 66%. Pick a higher gate. Do not lower it. (Where: `.github/workflows/tests.yml`; `code-standards.md`, Testing.)
- **S3. Add `.env` to `.gitignore` and `.dockerignore`.** Neither lists it, and no `.env` exists today (checked). Do it before anyone creates one.
- **S4. `docs/BUGS.md` has no row for #39.** Add it at the top (found by: the Render deployment; regression tests in `test_weather.py::TestRealForecastOnly`; fixed in PR #40). Update the status line, which was written before #39 (it counts 15 defects).
- **S5. Page: Chart.js blocked.** If the CDN is blocked, `drawChart` throws, the plan section never refreshes again, and the pill still says "Running normally". (Where: `frontend/index.html`; `ui-context.md`, Known UI Facts.)
- **S6. Page: `/api/live` returns `{}`.** Before the first tick the pill says "Running normally" while the sentence says "Waiting for the first reading…". (Same place.)
- **S7. Page: `/favicon.ico` returns 404.** There is no icon link.
- **S8. `/static/index.html` is served without the no-cache headers that `/` has.** (Where: `main.py` `_NOCACHE`.)
- **S9. `--cheap` is defined and never used.** The blue is hard-coded instead. Use the variable or remove it. (Where: `ui-context.md`, Theme.)
- **S10. Times before `/api/site` loads use the browser's time zone.**
- **S11. The savings month name and "Day N of M" use the server's UTC date, not plant time.**
- **S12. "N% of the bill" divides by the cost with panels and timer, not by the final "Still paid" figure.** The label and the maths disagree. (Where: `savings.py` `myenergy_pct_of_bill`; the violet row in the page.)
- **S13. README second pass.** Three differences from the page: the README calls the plan tile "the grid energy bought tonight" (the tile reads "Bought for the battery, next 24 h"); it names two status-pill problems (the page has four texts, adding "Readings delayed" and "Connecting…"); the "without Docker" command lacks `--loop asyncio --http h11`, which every other start command uses.
- **S14. Stale text in code.** The `weather.py` docstring says it "falls back to synthetic data" (no longer true for the live path). The `brain.py` header still says "never go below 10%" and has an old priority list. (Where: `code-standards.md`, Inconsistencies 15.)
- **S15. `/api/ask` validation errors return FastAPI's `{"detail": [...]}`, not `{"error": ...}`.** The page never sends bad input (it stops at 500 characters), so only direct callers see it. (Where: `main.py` `AskIn`; `architecture-context.md`, API, Error shapes.)
- **S16. The plan has fewer than 36 hours after 12:00 UTC.** Open-Meteo returns 48 rows from 00:00 UTC, so 25 hours are left at 23:00 UTC. This changes the plan length, so the decision-behaviour rules apply. (Where: `weather.py` `forecast_days=2`; `main._planning_forecast`; `architecture-context.md`, Known Limitations 11.)
- **S17. `context/AGENTS.md` and `context/CLAUDE.md` point to wrong or missing files.** `AGENTS.md` says "This is NOT the Next.js you know". `CLAUDE.md` names `context/architecture.md`; the file is `architecture-context.md`. **Agent 7 does this next.** Not done when this file was written.
- **S18. Stale statements in the other context files, now that this file exists.**
  - `code-standards.md` line 210 says `progress-tracker.md` "does not exist yet"; line 277 says it is "absent".
  - `code-standards.md` lines 11 and 277, `project-overview.md` line 137 and `architecture-context.md` line 546 say `ai-workflow-rules.md` describes a Next.js / shadcn project. The current `ai-workflow-rules.md` describes this project. The statement is wrong now.

## Open Questions

### (a) Owner decisions (an agent must not decide these)

1. **Objective.** Lowest cost (today), least grid kWh, or lowest CO2? Today the planner has no term for grid kWh or CO2, and it may buy more grid energy to cycle the battery. Affects Next Up step 2.
2. **"Battery full by time T."** Is it a hard requirement? If yes, at which time and level? Today nothing guarantees a charge level at a given time (the plan fills to 95% at about 18:00 and empties to 20% by about 22:00 on a clear day). Affects step 2.
3. **Target.** Real hardware (which inverters and battery; which protocol: Modbus, SunSpec, MQTT), or a simulator-based product? One plant or many? Affects steps 3 and 4.
4. **Dormant subsystems.** Delete them, or keep them as customer onboarding (an estimate for a prospect)? They are `estimate_service.py`, `pricing_service.py`, `facility_live.py`, `live_sim.py` (about 800 lines) with 6 routes. Also `/api/history`, `/api/forecast` and `/api/prices`, which neither the page nor the agent calls. Affects step 6. Do not delete or tidy around them until the owner decides.
5. **Savings realism.** The simulated month has one cloud value per day and is summer-like, so "cloudy now, sunny in two hours" never happens in it, and a full year would save less. The page also names the month with the real calendar month. How should this be made more realistic, or labelled? PR #38 changes the price side (Question 6) but keeps the weather simulated.
6. **PR #38.** Merge it, change it, or close it? It replaces the timer baseline with a price rule and changes the numbers the README and the context files quote. It will conflict with the uncommitted README correction. It touches the protected areas `savings.py` and `simulation/engine.py`.
7. **Scope for step 7.** A learned load forecast is machine learning, which `project-overview.md` lists as out of scope. Change the scope, or keep a fixed load profile?
8. **Commit the work of 2026-10-18?** The README correction is uncommitted and `context/` is untracked. Agents must ask before adding `context/` to git (`ai-workflow-rules.md`). Also decide the branch and PR for it.
9. **Three judgement calls that agent 5 made in `ai-workflow-rules.md`.** Please confirm or change each:
   - n8n workflow JSON (`automation/workflows/*.json`) may be changed only in n8n and re-exported. It is never edited by hand.
   - Agents write the text of GitHub issues, but open or close an issue only when the owner asks.
   - A defect found along the way is logged and fixed in its own unit, unless it blocks the current unit.

### (b) Known gaps and inconsistencies (not decisions; they need action)

The full lists are in `code-standards.md` (Inconsistencies, 21 items) and `architecture-context.md` (Known Limitations, 18 items). Only the items that need action are named here.

1. **If PR #38 is merged, update these together:** `README.md`; `project-overview.md` (Savings reporting, Success Criteria 5, Open Question 5); `architecture-context.md` (Savings Model, Key Decision D-8, Known Limitations 8, Invariant 9, test counts); `ui-context.md` (Savings section: "Battery on a simple timer", "A full month", the footnote); `code-standards.md` (honesty rules); `ai-workflow-rules.md` (Protected Areas: the timer baseline); and the test count (the PR text says 277 pytest tests).
2. **The AI evaluation was never re-run after the fixes for #28 and #29.** Where: `automation/README.md` (Results table), `docs/BUGS.md` (both rows say "re-run pending"). A run needs n8n, a Gemini key and the owner's go-ahead. The free tier allows about 9 questions a day, so the 20 cases need several days or a paid plan.
3. **GitHub issues that do not match the work** (agents do not close issues; the owner decides): #24, #25, #26 are open although PR #27 merged their work. #28 and #29 are open until the eval re-run. #34 and #35 are partly built (see M6 entry). #1 asked for a `documentation.md` write-up, and `architecture-context.md` now covers that. #3 (forecast accuracy) is Next Up step 5. **#20 (the planner treats the current hour as a full hour) is not recorded in any context file.** It is related to Known Limitations 7.
4. **Two solar scales and the one-hour shift** (`architecture-context.md`, Known Limitations 1 and 2). Next Up step 1.
5. **The live plant's solar comes from the forecast it plans with** (Known Limitations 3), so the planner never meets a forecast miss in the live loop. Next Up step 5.
6. **`import planner` or `import energy_manager` alone fails** (`ModuleNotFoundError: No module named 'engine'`). `import main` works. Next Up step 6. Do not reorder the imports in `main.py` meanwhile.
7. **`docs/DESIGN.md` is out of date** (four pages, "two brains", 152 checks, 6 `sys.path` edits; the code has one page, `energy_manager.py`, 276 tests, 7 edits). `ai-workflow-rules.md` says to leave it as history. Next Up step 6 says to refresh it. The owner chooses: refresh, mark as history, or remove.

## Assessment (2026-10-18)

A dated snapshot, moved here from the handoff file and lightly edited. It was written on 2026-10-18 by the agent that wrote `architecture-context.md`. I re-ran only the savings figures in part D; I did not re-check every other claim against the code. It is an opinion, not a plan. Re-read it before you act on it.

**Verdict: the decision core is the right architecture for this problem. The system around it is a prototype and is not yet an architecture for running a real factory.**

### What is right, keep it

- Forecast + LP + safety envelope + rule fallback is the standard, defensible pattern for battery energy management, and the layers have clear jobs.
- Keeping the LLM out of control, and grading it against the API, is the correct boundary.
- The honest-savings discipline and the regression-test habit are unusually good for a prototype.
- It works on the owner's scenario (`project-overview.md`, The Core Decision).

### A. What you want vs. what it optimises

1. **It minimises money, not grid kWh.** With a large price spread it will deliberately buy *more* grid energy at cheap hours to cycle the battery. If "use as little grid power as possible" is the real goal, add a price on grid kWh (or on CO₂) to the same LP; it is one coefficient.
2. **There is no "battery full by time T" requirement.** In a clear-sky run the plan fills the battery to 95% at about 18:00 and then empties it through the evening peak to the 20% reserve by about 22:00. Nothing guarantees a charge level at a given time. A hard requirement is a per-hour lower bound on the battery level in the LP.
3. **Battery wear is not in the LP.** The 0.04 €/kWh wear cost and 0.88 efficiency gate exist only in the fallback rules (`brain._arbitrage_worthwhile`). The live planner cycles the battery for any spread above its 10% round-trip loss.
4. **The forecast is treated as certain.** Safety rests on the 20% reserve and on re-planning. There is no margin that grows when the forecast is uncertain (for example, plan on a pessimistic solar value).

### B. Data problems that distort the "wait for the sun" decision (fix first)

1. **Two solar models disagree.** The live forecast converts irradiance at **1.00 × nameplate** at 1000 W/m² (250 kW on the demo plant). The clear-sky model used by the savings maths and the fallback peaks at **0.62 × nameplate** (155 kW). Real plants typically reach around 0.75–0.85 of nameplate after losses. The error runs in the dangerous direction: an overstated sun makes the plant wait for energy that will not arrive. (`weather.irradiance_to_solar_kw` vs `factory.SOLAR_PEAK_KW`.)
2. **The sun is read one hour late.** Open-Meteo documents `shortwave_radiation` as the *mean of the preceding hour*, but `weather._parse_open_meteo` treats the value stamped 12:00 as production for 12:00–13:00. "Sun in two hours" is planned as "in three". (DWD/Bright Sky semantics not checked.)
3. **In the live demo the plant's solar comes from the same forecast it plans with**, so the forecast is never wrong and the planner is never surprised. Robustness to forecast error is exercised only in the simulated-month savings run (15% error), not in the live loop.

### C. Structure

1. **No plant boundary.** The control loop calls `FacilitySimulator` methods directly. "In production this is replaced by the gateway" is a comment, not a seam. A real deployment needs a `Plant` interface (read telemetry, write setpoints, confirm they were applied) with a simulated and a hardware adapter, plus a fail-safe if readings stop. Today an exception in the loop is only printed.
2. **Flexible devices sit outside the optimiser.** The LP plans the battery against a *static* load profile (`expected_load_kw`: 90 kW by day, 27 kW at night). The EV charger and water heater are scheduled by rules after the fact. The two devices are created at import time with fixed deadlines and are never refilled once fulfilled.
3. **Site facts are scattered:** location and size in `simulator.py`, coordinates in `weather.py`, time zone and bidding zone in `prices.py`, thresholds in `brain.py`, defaults in `factory.py`. Battery limits are defined in four places (`factory`, `simulator`, `brain`, `models`).
4. **Import fragility.** `planner.py` and `energy_manager.py` import `engine`/`optimizer`/`factory` as top-level names and work only because another module has already edited `sys.path` (or because `pytest.ini` / the Dockerfile's working directory does).
5. **Dormant code.** About 800 lines and 6 endpoints serve no current page (plus `/api/history`, `/api/forecast` and `/api/prices`, which neither the page nor the agent calls). `docs/DESIGN.md` still describes four pages and "two brains" and is out of date: the UI is now one page and `energy_manager` already joins the planner and the rules.
6. **Single process and global state.** Fine now, a hard limit for more than one plant.
7. **Hourly slots:** the first slot's battery power is capped by *energy* available in the hour (38 kW observed instead of the 50 kW rating), so the setpoint decays as the battery nears the reserve. Acceptable for planning; a real-time layer should own power limits.

### D. Fit to the goal, honestly

On a fixed day/night tariff the planning layer is worth about **€40/month** on the demo plant (README; re-measured on 2026-10-18 with `savings.layers(30)`: €40.95). The panels and a timer do most of the saving. Planning matters most with **hourly prices**: `demo_dynamic_pricing.py` gives about €270/month (README; €266 on 2026-10-18 per `project-overview.md`), but that script uses simulated prices, a 100 kWp factory and a perfect forecast, so it is an upper bound. The unmerged PR #38 reports about €302/month on the last 30 days of real prices with a 15%-off forecast (PR text, simulated weather, not run by me). The value of "wait for the sun" is real but modest next to the panels themselves, and the project has no measured savings yet because there is no real plant.

## Architecture Decisions

Decisions an agent must respect. The full table is `architecture-context.md`, Key Decisions D-1 to D-15, and the Invariants list. The workflow rules are in `ai-workflow-rules.md`.

- **The planner proposes, the safety envelope disposes.** A plan reaches the plant only through `brain._follow_plan`. Never add a path that skips it (D-4; Invariant 3).
- **The rule engine stays as the fallback.** With no forecast or a failed solver, the rules decide (D-5).
- **Never plan with made-up weather.** No real forecast means rule mode and a visible status. Made-up prices only when labelled (D-6, D-7; Invariant 5).
- **Savings are layers, and the software is credited only for the gap to the baseline.** Never write a simulated number as a measured one (D-8; Invariant 9).
- **The LLM is outside the control path** and read-only. n8n stays private. The page talks only to myEnergy (D-9, D-10; Invariant 10).
- **The reason sentence must match the power flow** (D-13; Invariant 7).
- **Plant-local time** for tariffs, load pattern and CO2; UTC everywhere else (D-14; Invariant 8).
- **One process, one worker, one plant.** State lives in module globals (D-11; Invariant 12).
- **Tests never reach the internet** (D-15; Invariant 11).
- **The objective is cost only** until the owner answers Open Question 1.
- **Protected areas** need a task that says so: `simulation/engine.py` physics, the savings baselines, the safety constants, the n8n JSON, secrets, `data/myenergy.db` (`ai-workflow-rules.md`).
- **Python 3.9 is the floor** (the local `.venv`); Docker and CI use 3.11 (`code-standards.md`, Python).

## Session Notes

Practical notes for agents. They come from the agents' reports and from what I ran on 2026-10-18.

- **Python.** The local `.venv` is Python 3.9.6. Docker and CI use 3.11. Code must run on both.
- **Test command.** Run `.venv/bin/python -m pytest -m "not e2e"` from the repo root. It takes about 3 s. **Do not add `-q`**: `pytest.ini` already has `addopts = -q`, and a second `-q` hides the summary line (I got only dots). To see "268 passed" use no extra flag, or use `-o addopts=""` with `-q`.
- **Browser tests** need `playwright install chromium` once. Run them with `-m e2e` only when you changed the page or an API field the page reads.
- **Imports.** `planner.py` and `energy_manager.py` cannot be imported alone. `import main` works, and so does running from pytest (`pytest.ini` sets the path). Do not reorder the import lines in `main.py`.
- **Simulation scripts** must be run from inside `simulation/`, for example `cd simulation && ../.venv/bin/python demo_dynamic_pricing.py`. A `cd` in one shell command can stay in the next one: use absolute paths.
- **The two standalone proofs** (`verify_simulation.py`, `test_decisions.py`) exit 0 even on FAIL. Read their output for `FAIL`. Both passed on 2026-10-18.
- **Running the app has side effects.** It calls the real weather APIs (Open-Meteo, Bright Sky) and the real price API (Energy-Charts) at startup and every 30 minutes, and it writes `data/myenergy.db` (git-ignored). Start it with `cd backend && ../.venv/bin/python -m uvicorn main:app --port 8000 --loop asyncio --http h11`. Stop it when you are done.
- **The AI evaluation** (`automation/evals/run_eval.py`) uses real Gemini quota. The free tier allows about 9 questions a day. Do not run it unless the owner asks. The grader and workflow tests use no quota.
- **Weather timestamps.** Open-Meteo's documentation confirms that radiation is the mean of the **preceding** hour. Bright Sky's timestamp meaning is **unverified**.
- **Git.** Do not commit, push, open a PR, or open or close an issue unless the owner asks. `context/` is untracked and `README.md` is modified. `gh` works in this environment (`gh issue list`, `gh pr list`, `gh run list`); the state in this file is from 2026-10-18.
- **Keep this file true.** When you finish a unit: add a Completed entry (say what you did not verify), update Current Goal and In Progress, and move finished items out of Next Up.
