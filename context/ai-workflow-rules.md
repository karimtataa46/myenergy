# Development Workflow

## Approach

Build this project in small steps, from the context files. They define what to build, how it is built and where the work stands. Implement against them. Never infer or invent behaviour.

- What the system is: `project-overview.md`, `architecture-context.md`, `ui-context.md`. How code, tests and commits are written: `code-standards.md`. State of the work: `progress-tracker.md`. This file does not repeat them.
- A **unit of work** is one GitHub issue (`#N`) or one request from the owner. It gets its own branch and its own pull request. The history shows it: #31 (`m6-p1-price-source`), #32 (`m6-p2-hourly-decisions`) and the defect #39 (`fix-real-weather-only`) each have a branch and a PR.
- A big goal is cut into parts first (M6 has P1 to P5), one issue per part. Do the part you were asked for, not the next one. Before you start, look at `git branch -a` and `gh issue list` for a branch or issue that already covers it.
- myEnergy is a learning and CV prototype. Honesty of numbers and claims is part of "done". A simulated result is called simulated. A thing is "verified" only if you ran it. Never make the plant, the savings or a test look better than it is.

## Scoping Rules

- Work on one unit at a time.
- Prefer small, verifiable increments over large speculative changes.
- Do not combine unrelated system boundaries in a single step.
- Do not fix the items in `code-standards.md` "Inconsistencies" on the side. Each one is its own change, with the owner's agreement.
- A defect you find on the way: write it up (issue text and a `docs/BUGS.md` row) and fix it in its own unit, unless it blocks the current one.

The boundaries of this system (`architecture-context.md`, System Boundaries):

- the decision engine: planner and LP, safety envelope, fallback rules, device rules (`planner.py`, `brain.py`, `energy_manager.py`, `simulation/optimizer.py`)
- the control loop and the simulated plant (`main._control_loop`, `simulator.py`)
- external data: weather and prices (`weather.py`, `prices.py`)
- the savings model (`savings.py`, `simulation/engine.py`, `controllers.py`)
- storage (`database.py`) and the API (routes in `main.py`)
- the operator page (`frontend/index.html`)
- the AI assistant: `assistant.py`, the n8n workflows and the evaluation (`automation/`)
- tests and CI (`tests/`, `.github/workflows/tests.yml`)
- deployment (`Dockerfile`, `docker-compose.yml`, `render.yaml`)

## When To Split Work

Split an implementation step if it combines, for example:

- a change to decision behaviour (what the battery or a device does) and a change to the operator page
- the control loop or simulated plant and the savings simulation (they share the LP but use different tariffs and limits)
- a new data source and the decision change that uses it (M6 did this in two PRs: #31, then #32)
- the live system and the dormant developer APIs (`estimate_service`, `pricing_service`, `facility_live`, `live_sim`)
- backend behaviour and the n8n workflows or the eval set
- a refactor (moving code, making packages, changing imports or `sys.path`) and a behaviour change
- behaviour that is not clearly defined in the context files

One exception: renaming or removing an API field is one unit together with all its readers (`code-standards.md`, FastAPI and the API).

If a change cannot be verified end to end quickly, the scope is too broad. Split it.

## Handling Missing Requirements

- Do not invent product behaviour that is not defined in the context files.
- If a requirement is ambiguous, resolve it in the relevant context file before you implement. If only the owner can answer, ask.
- If a requirement is missing, add it as an open question in `progress-tracker.md` before you continue.
- When code and docs disagree, the code wins. Fix the doc in the same change.

These decisions are open (`project-overview.md`, Open Questions). Do not decide them, and do not build toward one answer:

1. The objective: lowest cost (today), least grid kWh, or lowest CO2. Do not add a grid-kWh or CO2 term to the LP.
2. Whether "battery full by time T" is a hard requirement, and which time and level.
3. Real hardware (which inverter, which protocol) or simulator only.
4. The dormant subsystems: delete or keep. Do not delete them, and do not tidy around them.

Also the owner's call: a route or assistant tool that changes plant state, user accounts or authentication, storing more than the 24 hours of snapshots, a database schema change.

## Changes To Decision Behaviour

A wrong change here costs money or safety. It means anything that changes what the battery or a device does, or the sentence that explains it (`planner.py`, `brain.py`, `energy_manager.py`, `simulation/optimizer.py`, the plant rules in `main._control_loop`). It needs all four:

1. The owner's request, or an agreed issue.
2. A test that shows the new behaviour. Prefer an outcome test like `tests/test_acceptance.py`: real physics, two days that differ in one thing, then assert kWh, money and SoC. Add the rule tests in `test_brain.py` as well (`code-standards.md`, Decision Engine and Safety).
3. Every invariant in `architecture-context.md` (Invariants) is still true.
4. The reason sentence still matches the power flow (`test_the_sentence_matches_the_actual_power_flow`).

Also:

- Never weaken the safety envelope to make a test pass. If a test fails against the envelope, the plan or the test is wrong.
- Never add a path that skips `brain._follow_plan`.
- Never make savings or results look better than they are. After you change the LP or the savings model, run `savings.layers(30)` and update the numbers in `README.md`, `project-overview.md` and `architecture-context.md` together.
- Never plan with made-up weather. Made-up prices only when labelled (`code-standards.md`, General, Honesty rules).

## Protected Areas

Do not change these unless the task says so. If it does, follow the "To change" step.

- **Third-party code and `.venv/`.** Why: it is not ours. To change: never edit inside `.venv/`. To use another library version, change the pin in `requirements.txt` and run all tests.
- **The physics in `simulation/engine.py`.** Why: it is the validated core. The live plan, the savings and the proofs all depend on it. To change: only for a physics task. Run both standalone proofs (see Verification), run `savings.layers(30)`, update the README numbers.
- **The honest baselines: `backend/savings.py` and `controllers.timer`.** Why: they decide what the software is credited for. A weaker timer or a better forecast makes the software look better than it is (the old EUR 740 claim). To change: only with the owner's agreement. Keep `tests/test_savings.py` passing.
- **The safety constants and envelope in `brain.py`** (`BATTERY_RESERVE_SOC` 20, `BATTERY_FULL_SOC` 95, `BATTERY_CRITICAL_SOC` 15, the order of steps in `_follow_plan`) **and `DEMAND_TARGET_KW` in `main.py`.** Why: a drained battery or an export from the battery cannot be undone. To change: only for a task about a safety limit. Also pass it to the planner through `energy_manager.plan_for`, update the tests and the Invariants.
- **The n8n workflows, `automation/workflows/*.json`.** Why: they are exported from n8n. A hand edit is lost at the next export. To change: edit in the n8n editor, then export back (`n8n export:workflow --id=... --pretty --output=/workflows/...`, see `automation/README.md`) and run `tests/test_workflows.py`. If n8n is not running, describe the change for the owner. Do not hand-edit.
- **Secrets:** `.env` files, API keys, the Gemini key (it lives in n8n's credential store). Never read, print or commit them. No `.env` exists today, and `.gitignore` and `.dockerignore` do not list it: add it to both before you create one.
- **`data/myenergy.db`.** Why: runtime data. Never commit it, edit it or quote it in docs as a result. To change the schema: tell the owner first. There is no migration tool, and an old file keeps its old columns.

## Verification

Run it. Do not assume.

- Before you finish, from the repo root: `.venv/bin/python -m pytest -m "not e2e"`. It takes a few seconds and must pass.
- If you changed the page or an API field the page reads, also run the browser tests: `.venv/bin/python -m pytest -m e2e` (once: `playwright install chromium`).
- If you changed `simulation/engine.py`, `optimizer.py` or `factory.py`, also run `cd simulation && ../.venv/bin/python verify_simulation.py && ../.venv/bin/python test_decisions.py`, and read the output for FAIL. These scripts exit 0 even when a check fails, so CI does not catch it.
- If the behaviour matters (loop, plan, page, API shape), start the app and look: `cd backend && ../.venv/bin/python -m uvicorn main:app --port 8000 --loop asyncio --http h11`. One process. Stop it when you are done.
- Running the app has side effects. It calls the real weather APIs (Open-Meteo, Bright Sky) and the real price API (Energy-Charts) at startup and every 30 minutes, and it writes `data/myenergy.db` (git-ignored).
- The AI evaluation (`automation/evals/run_eval.py`) uses real model quota and needs n8n and a key. The free tier allows about 9 questions a day. Do not run it unless the owner asks. The grader and workflow tests (`test_eval_grading.py`, `test_workflows.py`) use no quota.
- Tests never reach the internet (autouse `no_internet` in `tests/conftest.py`). Do not remove or bypass it. A new fetch needs a function that `mock_network` can replace. The browser in the e2e tests is a separate process and still loads Chart.js from the CDN.
- Never state a number you did not run. Savings and timings come from running `savings.layers(...)` or the script, not from memory or from the docs.
- In the final report, say what you verified and how (which command, how many tests passed), and what you did NOT exercise. For example: browser tests not run, app not started, real APIs not called, eval not re-run, Python 3.11 not tried (`.venv` is 3.9, CI is 3.11). Do not write "all tests pass" if you ran only some.

## Keeping Docs In Sync

Update the relevant file in the same change as the code:

- architecture, boundaries, routes, constants, invariants: `architecture-context.md`
- the page: `ui-context.md`
- conventions: `code-standards.md`
- scope, product behaviour, open questions: `project-overview.md`
- state of work: `progress-tracker.md`
- user-facing claims, numbers, test counts: `README.md`. It must stay honest. Simulated numbers are labelled simulated and name the script.
- a fixed defect: `docs/BUGS.md`, with the workflow in `code-standards.md` (Defects and Docs)

When a number changes (savings, test count), change the README, `project-overview.md` and `architecture-context.md` together.

`docs/DESIGN.md` is history, not a spec. Do not rewrite it on the side.

Progress must reflect the actual state of the implementation, not the intended state. Write down what was not verified.

## Git

This is what the history shows. The formats are in `code-standards.md` (Git and Pull Requests).

- Work on a branch, not on `main`. One unit per branch and PR. Use `fix-<what>` for a defect.
- Reference the issue in the commit subject: `(closes #N)`, `(fixes #N)`, `(part of #N)`.
- A fix and its regression test go in the same commit.
- CI must pass (`.github/workflows/tests.yml`: pytest with the coverage gate, then the two proofs).
- **Never commit, push or open a PR unless the owner asks.** The same goes for creating or closing a GitHub issue. Write the text and give it to the owner: goal and definition of done for a feature; found by, repro, cause, fix and regression tests for a defect.
- Never commit what `.gitignore` lists. `context/` is untracked today: ask the owner before you add it.

## Before Moving To The Next Unit

1. The unit works end to end within its scope, and the tests pass (see Verification).
2. No invariant in `architecture-context.md` was violated.
3. Any fixed defect has a regression test and a row in `docs/BUGS.md`.
4. The context files and the README describe the new state.
5. `progress-tracker.md` reflects the completed work, including what was not verified.
