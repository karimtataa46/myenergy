# Code Standards

> How code is written in myEnergy. Read it before you change code, after `project-overview.md`,
> `architecture-context.md` and `ui-context.md` (this file does not repeat them).
> Checked on 2026-10-18 against commit `eea63ab` plus the working tree. Python 3.9.6: 268 non-browser tests pass.
>
> **There is no linter, formatter or type checker** (no `pyproject.toml`, ruff, black, flake8, mypy).
> Every rule here comes from (a) a pattern the code follows, (b) a written rule (comment, README,
> `BUGS.md`, `DESIGN.md`) or (c) a test. The source is in brackets when it is not obvious.
> Where the code disagrees with itself, see **Inconsistencies**. Do not "fix" those on the side.
> Do not take stack rules from `context/AGENTS.md` or `context/ai-workflow-rules.md`: they describe a Next.js project.

## General

- Keep modules small and single-purpose. `energy_manager.py` is 52 lines and only joins `planner` and `brain`. `main.py` (579 lines) is the largest and should not grow logic: put it in a module.
- Fix the root cause, not the symptom. Follow the `BUGS.md` workflow (see Defects and Docs). The fix and its regression test go in the same commit (fix commits `247d67a`, `96a7837`, `bfc7d2f`, `4db76a1`, `5d01a28`).
- One definition per fact. `simulator.DEMO_CFG` is "ONE config for everything" (`simulator.py` comment): the loop, the planner, `/api/site` and `savings.py` all read it. `factory.py`: "All the physical facts about the site live here". `engine.HORIZON_HOURS` is the one horizon. Before you add a number, search for it. Never add another copy of a site fact (battery size, SoC limits, tariff, location). The existing copies are listed in Inconsistencies.
- Comments are plain English and explain WHY, not what. Cite the bug when a line exists because of a defect: `(#18)`, `(bug #12)`, `(#39)`.
- Honesty rules. The code and the tests enforce them. Never weaken them:
  - Never plan with made-up weather (#39; `test_weather.py::TestRealForecastOnly`).
  - Made-up prices only when labelled (`prices.SOURCE_SIMULATED`; `test_prices.py`).
  - Report the software's savings only against the battery-on-a-timer baseline (`savings.layers`; `test_savings.py::TestLayers`).
  - The reason sentence must match the power flow (#22; `test_brain.py::TestFollowPlan::test_the_sentence_matches_the_actual_power_flow`).
  - The story never credits the sun without a counterfactual (`planner.summarize`; `test_planner.py`).
  - Simulated numbers are never written as measured results (README "What it saves, honestly").
- Respect the boundaries in `architecture-context.md` (System Boundaries). In short: `simulation/` never imports `backend/` (checked); battery physics stays in `simulation/`; `_control_loop` never touches `assistant`; `automation/` is never imported by `backend/`; the page talks only to myEnergy.
- Never break green. Run `.venv/bin/python -m pytest -m "not e2e"` before you commit. CI runs everything on every push and pull request (`DESIGN.md` principle "Never break green").
- Write operator-facing text for a factory operator: short sentences, plain words, no jargon (`project-overview.md` goal 5; the page and `planner._explain`).

## Python

**Version floor: Python 3.9.** The local `.venv` is 3.9.6. Docker, `runtime.txt` and CI use 3.11. Code must run on both.
- Never use features from 3.10 or later. None of the common ones appear in the repo (checked): no `X | None`, no `match`, no `zip(strict=)`, no `dataclass(slots=True / kw_only=True)`.
- Write optional values as `Optional[X]` (`brain`, `models`, `planner`, `prices`, `main`, `simulator`). Write collections with `typing` names: `List[X]`, `Dict[K, V]`, `Callable`. `weather.py` and `database.py` use built-in `list[...]`. That works on 3.9, but in a file that already uses `typing` names, keep using them.
- Do not add `from __future__ import annotations` to use `|`. Only `models.py` has it.

**Types.** Annotate all parameters and the return type of new functions. Use plain `float`, `int`, `str`, `bool`. Annotate only what is true: a value that can be `None` is `Optional`.

**Dataclasses.**
- Use plain `@dataclass` for state and records (`models.py`, `planner.py`, `engine.py`, `factory.FacilityConfig`). Use `@dataclass(frozen=True)` for a value that must never change after creation (`prices.HourPrice`).
- Put fields with defaults last. Use `field(default_factory=...)` for lists and dicts (`Plan.hours`, `EnergyDecision.device_commands`).
- Put the unit and meaning in a trailing comment on each field: `power_kw: float  # positive = charging, negative = discharging`.
- Make a changed copy with `dataclasses.replace(...)`. Never mutate a shared config. (`simulator.DEMO_CFG`, `planner.make_plan`'s `plan_cfg`, `energy_manager.decide`, `savings.layers`.)
- Give new `BrainInput` fields a default, so old callers and the no-forecast path still work (every planner field has one).

**Enums.** There is one: `GridAction(str, Enum)` in `models.py`, lower_snake string values. Send `.value` in JSON (`decision.action.value`). Any new enum that goes into JSON uses the same pattern.

**Naming.**
- Modules: `lower_snake.py`. Functions and variables: `snake_case`. Classes: `PascalCase`.
- A leading underscore marks a private helper or module-private constant: `_follow_plan`, `_explain`, `_apply_battery`, `_parse_open_meteo`, `_NOCACHE`, `_SITE_TZ`. Tests may import private helpers.
- Constants are `UPPER_SNAKE` at the top of the module, with a trailing comment: `BATTERY_RESERVE_SOC = 20.0  # % ...`.
- Put the unit in the name: `_KW`, `_KWH`, `_EUR_KWH`, `_HOURS`, `_MINUTES`, `_SECONDS`. For variables and JSON keys: `_kw`, `_kwh`, `_eur`, `_pct` (percent), `_frac` (fraction 0 to 1; `min_soc_frac`). Spell time units out. `assistant.py` has `_S`; do not copy it.
- Tunable thresholds are named constants at the top of the module (`brain.py`: "Thresholds, these are the tunable parameters of the engine"; `planner.SUN_CREDIT_KWH`). Never hard-code `20`, `95`, `15` in decision code: import `brain.BATTERY_RESERVE_SOC`, `BATTERY_FULL_SOC`, `BATTERY_CRITICAL_SOC`.

**Docstrings and comments.**
- Every module starts with a docstring that says what it is for and why it is built this way (all do, except `models.py`).
- Functions get a `"""..."""` docstring in free text: what it returns and when it returns `None`. There are no `Args:` / `Returns:` sections anywhere. Do not add them.
- Use end-of-line comments for units and reasons. Use `# ── Title ───` banners to split a file (`main.py`, `simulation/*`, `conftest.py`).
- Python files are UTF-8. `€`, `—`, `→`, `²` appear in comments. See "Reason sentences" below for user-facing text.

**Imports.**
- Order: standard library, third party, local. One blank line between groups (`planner.py`, `energy_manager.py`, `assistant.py`, `prices.py`).
- Import local modules as top-level names: `import brain`, `from models import X`. Never `from backend.x`, never relative imports.
- Fixed aliases: `import factory as F` (everywhere). In `main.py`: `weather_module`, `sim_module`, `prices_module`, `savings_module`, `live_sim_module` (so they do not clash with local names like `prices`).
- After a `sys.path` edit, mark the imports `# noqa: E402`, even though no linter runs.
- Do not import inside functions in app code (only the dormant `facility_live.py` and `live_sim.py` do). Tests may.

**Strings and format.**
- Use f-strings. Use double quotes in Python (960 against 16 single-quoted strings in `backend/`). `str.format` appears only for a constant URL template (`prices.API`).
- 4 spaces, no tabs. No line limit is enforced. Most lines are under 100 characters; the long ones are data tables and strings. Wrap new code the same way.
- Only `main.py` prints. Use `print(f"[area] message")` with a bracketed prefix (`[weather]`, `[control loop error]`). There is no `logging` module. Never print in `brain`, `planner`, `weather`, `prices`.

**Errors.**
- A function that cannot answer returns `None` and the caller falls back. It does not invent a value. `optimal_battery_schedule` returns `None` on a solver failure, `make_plan` returns `None` with no hours, `energy_manager.decide` then calls the rules.
- Give each boundary its own exception with a message written for the operator: `weather.ForecastUnavailable`, `assistant.AgentError` / `AgentTimeout`.
- Catch `Exception` only around I/O (`weather.fetch_real_forecast`, `PriceBook.refresh`, `search_cities`) and the control-loop tick. Never use a bare `except:`. Decision code (`brain`, `planner`, `optimizer`) has no `try`. Keep it so bugs show up in tests.

**Randomness.** Anything that feeds tests or savings figures is seeded (`generate_month_weather(seed=42)`, `forecast_of(seed=1)`; factory: "Seeded so every test run is identical"). Only the live demo noise in `simulator.py` is unseeded.

**Pure first.** `make_plan`, `summarize`, `optimal_battery_schedule`, `engine.step` take values and return values. Network, SQLite and clocks live in `weather`, `prices`, `database`, `assistant` and `main`. Pass `now` as a parameter (`_plan_response(now=None)`, `PriceBook.next_hours(now, n)`) so tests can fix the time.

**Reason sentences (user-facing text).** Follow `planner._explain` and `brain._follow_plan`:
- One sentence. A space between number and unit ("12 kW", "158 kWh"). `€` before the number ("€0.28"). Whole numbers (`:.0f`) for kW and kWh, `:.2f` for prices.
- No em dashes. `planner.py` and `index.html` have none; the agent prompt is tested for it (`test_workflows.py::test_the_prompt_has_no_em_dashes`). Use commas, colons or semicolons.
- The older fallback sentences in `brain.decide` (rules 1 to 6) break all three rules. Do not copy them.

## Units, Signs and Time

| Thing | Convention | Where |
|-------|-----------|-------|
| Power | kW. Energy: kWh. In a one-hour slot kW equals kWh numerically | `PlanningForecast.load_kwh`, `engine.StepState` |
| Energy in a tick | `kW * dt_seconds / 3600` (tick = 5 s) | `main._control_loop`, `FacilitySimulator.apply_decision` |
| `battery_kw` | positive = charging, negative = discharging | `BatteryState.power_kw`, `EnergyDecision`, `Plan.battery_kw`, `engine` `battery_ac_kwh` |
| `grid_kw` | positive = importing, negative = exporting | `EnergyDecision.grid_kw` |
| Snapshot grid | `grid_import_kw` and `grid_export_kw`, both `>= 0` (`+ 0.0` removes `-0.0`) | `simulator.get_grid`, `/api/live` |
| SoC, percent (0 to 100) | `BatteryState.soc_percent`, `brain.BATTERY_*_SOC`, `PlanHour.battery_pct`, `/api/live` `battery_soc` | `models.py`, `brain.py` |
| SoC, fraction (0 to 1) | `FacilityConfig.battery_min_soc / battery_max_soc`, `make_plan(min_soc_frac, max_soc_frac)` | `factory.py`, `planner.py` |
| SoC, energy | `soc_kwh`. `StepState.soc_pct` is a FRACTION despite its name | `engine.py` |
| Prices | EUR/kWh as floats (0.28). EUR/MWh only inside `prices.hourly()`, which divides by 1000 | `prices.py` |
| Buy / sell price | `buy = market + 0.10`; `sell = max(market - 0.01, 0)` | `prices.to_hour_price` |
| CO2 | kg; intensity kg/kWh | `factory.CO2_*` |

- Convert between percent and fraction only at one boundary, with an explicit `/ 100.0` or `* 100`. Name the unit (`_pct`, `_frac`) so the next reader sees it (`energy_manager.plan_for` divides by 100).
- Beware two opposite signs in `brain.py`: `deficit = total_load - solar` in `_follow_plan` (negative = surplus) and `net_solar = solar - total_load` in `decide` (positive = surplus). Write the sign in a comment next to a new variable, as `brain.py` does.
- Round at the edge where numbers leave the system (`_plan_response`, `_prices_response`): kW to 1 decimal, prices to 3, plan KPIs to whole numbers. The page must show API values unchanged (`test_e2e.py`: `#k-buy` equals `buy_tonight_kwh`).
- **Time is UTC inside.** Use `datetime.now(timezone.utc)`. Never `utcnow()` or a naive `datetime.now()` (none in the repo, checked). Every datetime is timezone-aware. Stored timestamps are ISO-8601 UTC strings, compared as text (`database.py`).
- **Plant-local time only through `simulator.site_hour(dt)`** (hour of day in Europe/Berlin, with summer time) for tariff, work pattern and CO2, and through `ZoneInfo(sim_module.DEMO_TIMEZONE)` / `prices.SITE_TZ` for labels. Never use `dt.hour` of a UTC datetime to choose a tariff or a load (#18; `tests/test_site_time.py`).
- Send times to the page as an ISO UTC string plus a plant-local `label` ("HH:MM", built in `main._plan_response`). The page does not convert (`ui-context.md`).
- Slot 0 is the current hour: the forecast row stamped with the current UTC hour and the price of that hour. `PlanHour.battery_pct` is the level at the END of hour k; `/api/plan` `hours[k].battery_pct` is the level at the START (shifted by `main`). Keep that shift when you touch either.
- In tests use fixed instants, not `now()`, whenever the hour matters (`SUMMER_2130_UTC` in `test_site_time.py`; the flaky-test fix `1c7bdf8`).

## Decision Engine and Safety

See `architecture-context.md`: Decision Engine, Safety envelope, Invariants. Rules for changing it:
- **The planner proposes, `brain._follow_plan` disposes.** The loop calls only `energy_manager.decide`. A plan reaches the plant only as `planned_battery_kw` inside `brain.decide`. Never apply a plan, or a new controller, straight to `facility.apply_decision`. Never add a path that skips the envelope.
- A new safety limit goes into `_follow_plan` and into the fallback rules. Also pass it to the planner through `energy_manager.plan_for` (as `min_soc_frac` and `max_soc_frac`), so the plan does not ask for something the envelope refuses (`planner.make_plan` comment).
- Keep the order inside `_follow_plan`: clamp to inverter limits, then reserve and no-export on discharge, then full / grid allowance / demand cap on charge, then action, then reason. Add new steps before the action is chosen, so `action`, `grid_kw` and `reason` are computed from the final setpoint.
- Every `EnergyDecision` has a one-sentence `reason` that agrees with `action`, `battery_kw` and `grid_kw`. When the envelope changes the plan, the reason says so. Add a case to the parametrized `test_the_sentence_matches_the_actual_power_flow` for each new sentence.
- The fallback rules must work without a forecast: `brain.decide` with `planned_battery_kw=None` uses only `BrainInput`. Never make a forecast-only value required. (`test_planner.py::TestEnergyManager::test_without_a_forecast_it_falls_back_to_the_rules`.)
- Treat anything under 0.5 kW as zero when you compare setpoints (#19). Use `1e-9` / `1e-6` for float equality, as `brain.py` does.
- Optional devices never exceed the 95 kW demand ceiling. Forced devices may. Min-on and min-off locks hold unless a deadline forces the device. Only the control loop sets `last_change_at`.
- `optimal_battery_schedule` returns a dict or `None`. Every caller must handle `None`.
- The objective is cost only (Open Question 1, `project-overview.md`). Do not add a grid-kWh or CO2 term without the owner.
- The savings model and the live planner share the LP. When you change the LP, re-run `savings.layers(30)` and update the README numbers.
- A new decision behaviour needs two tests: an outcome test through `energy_manager.decide` (see Testing) and a rule test in `test_brain.py`.

## FastAPI and the API

- Handlers are `async def` and thin: call a helper, return a dict. Logic lives in plain functions (`_plan_response`, `_prices_response`, `_site_info`) that tests can call directly.
- Run blocking or slow work with `await asyncio.to_thread(fn, ...)`: network, the LP, the savings simulation (0.4 s), the n8n call. Existing: `/api/plan`, `/api/savings`, `/api/assistant`, `/api/ask`. Quick in-memory reads run on the loop.
- Never add network calls to the 5-second tick. The tick runs on the event loop. Weather and prices refresh in their own loop (`_forecast_refresh_loop`, 30 min). Live-path handlers read the cache and never fetch.
- Request bodies are Pydantic `BaseModel`s with limits, like `AskIn` (`Field(min_length, max_length, pattern)`). `EstimateIn` has none and is dormant: do not copy it. Strip and re-check text (`question.strip()`).
- Responses are plain dicts with `snake_case` keys and the unit in the name (`solar_kw`, `buy_tonight_kwh`, `cost_saved_eur`).
- Never rename or remove a field of `/api/live`, `/api/plan`, `/api/savings` or `/api/site` without updating all readers: `frontend/index.html`, `tests/test_e2e.py`, the tool descriptions in `automation/workflows/*.json`, `automation/evals/cases.json` (`live.battery_soc` style paths). Adding a field is safe.
- **Errors.** `{"error": message}` with a real HTTP status through `_ask_error()`; only `/api/ask` does this today (422, 429, 503, 504). Write the message for the operator, in plain English, with no exception text. A normal "no data yet" state is HTTP 200 with `available: false` and a `message` (`/api/plan`). Pydantic's own 422 uses `{"detail": [...]}`. The dormant routes return 200 with `{"error": ...}`: do not copy that.
- Removed pages return 404 (`test_api.py::TestPages`). `/` is served by `_page()` with `_NOCACHE` headers. Do not add caching or a service worker.
- The API has no authentication and CORS is `*`. Every route is read-only except `POST /api/ask` (it relays a question). A route that changes plant state needs a decision from the owner.
- State lives at module level in `main.py` (table in `architecture-context.md`, Runtime Model). Data shared with threads uses `_forecast_lock`: copy under the lock (`fc = forecast_cache[:]`), replace the whole list, never change it in place. Set cache, time, source and error together in one `with` block.
- One process, one worker. Start commands always have `--loop asyncio --http h11` and never `--workers`.
- Startup goes in `lifespan`; background loops are `asyncio.create_task`. A loop body is wrapped so one failure does not stop the loop, then `await asyncio.sleep(...)`.
- Name new handlers `api_<name>` (older ones are `get_<name>`). Put a one-line docstring on each: it shows in `/docs`. Place a route with its group; dormant routes stay under their "Developer APIs" banner.

## External Data

- Use `urllib.request.urlopen(url, timeout=N)` with an explicit timeout (8 s weather and prices, 3 s probe, 6 s geocoding, 90 s agent). `requirements.txt` has no HTTP library. Do not add one.
- Split a feed into a fetch function that raises on any failure and a pure parser (`fetch_open_meteo` / `_parse_open_meteo`, `fetch_dwd` / `_parse_bright_sky`, `fetch_market` / `hourly`). The caller decides the fallback. Tests feed the parser a dict.
- **Weather order:** Open-Meteo, then DWD (Bright Sky), then raise `ForecastUnavailable` with one reason per source (cut to 200 characters). The live plant keeps its last real forecast. With none, it runs on the rules and says so (`/api/plan` `available: false`, status pill). The live path calls `fetch_real_forecast` only. Never call `weather.fetch_forecast` there: it falls back to a synthetic forecast (developer APIs only) (#39).
- **Prices:** real data, else keep the last real data, else the simulated model labelled `SOURCE_SIMULATED`. Hours not yet published are copied from a day earlier and flagged `estimated=True`.
- Label every source and carry the label to the API (`forecast_source` in `/api/plan`, `price_source` in `/api/site`). Keep the attribution string: `SOURCE_REAL = "Bundesnetzagentur | SMARD.de (CC BY 4.0), via Energy-Charts"`.
- Look network functions up at call time, through the module, so tests can replace them: `weather_module.fetch_real_forecast(...)` in `main.py`, `(self._fetch or fetch_market)` in `PriceBook.refresh` (comment: "looked up at call time"). Never write `from weather import fetch_real_forecast` in `main.py`.
- **Tests never reach the internet** (autouse `no_internet` in `conftest.py`). Every new fetch needs a module-level function that `mock_network` can replace. If the app calls it at startup (`lifespan`), add the patch to `mock_network`.
- **AI assistant.** Browser to `/api/ask` to `assistant.ask` to n8n. The only setting is the `AGENT_URL` environment variable. n8n workflows call only existing GET endpoints through `{{ $env.MYENERGY_URL }}`, with no hard-coded host and no keys in the JSON, one language model each, tool descriptions over 100 characters that explain fields and units, and no em dashes in the system prompt. `test_workflows.py` checks all of it. After an API change, update the tool descriptions and `cases.json`, then run `tests/test_workflows.py` and `tests/test_eval_grading.py`.
- `automation/evals/` uses the standard library only. `grading.py` stays pure (no network) and tested.

## Data and Storage

- SQLite only through `database.py`. No SQL anywhere else. Open a connection per call with `with _conn() as conn:`. Use `?` placeholders, never f-string SQL.
- Store only the 5-second snapshot columns, for 24 hours (`RETENTION_HOURS`, pruned in `insert_snapshot`). Plans, forecasts, prices and measured savings are not stored (`architecture-context.md`, Storage Model). Storing more is a decision for the owner.
- There is no migration tool and the table uses `CREATE TABLE IF NOT EXISTS`. An old `data/myenergy.db` keeps its old columns. Tell the owner before a schema change.
- `data/*.db` is git-ignored and Docker-ignored. Never commit data files.
- No secrets in the repo. The Gemini key lives in n8n's credential store (the `n8n_data` volume). The only variables in code are `AGENT_URL` and `PORT`. `test_workflows.py::test_no_secrets_are_committed` checks the workflows. `.gitignore` and `.dockerignore` do not list `.env` yet: add it to both before you create one.

## Frontend

The visual rules are in `ui-context.md`. Code rules:
- One file, `frontend/index.html`: vanilla JS in one classic `<script>` (not a module), no framework, no build step. Chart.js (pinned `4.4.0` in the URL) is the only external script. Do not turn the script into a module: `test_e2e.py` calls the global `loadLive()` and `loadPlan()`.
- Style: `const` / `let` (no `var`), single quotes, semicolons, 2-space indent, template literals, small arrow functions, `$ = id => document.getElementById(id)`. Banners: `/* ── 1. right now: ... ── */`.
- Keep the pattern `loadX()` (fetch, set `state.x`, call `renderX()`) and one `state` object. `renderX()` only reads `state` and writes the DOM.
- Fetch with `getJSON` (`cache: 'no-store'`, throws on non-OK) and `fetchOrNull`. Catch only the network call. Never wrap rendering in `try/catch` (comment: "an error while rendering is a bug and must surface").
- Fixed polling uses `setInterval`. When the next delay depends on the result, chain `setTimeout` and `clearTimeout` the old timer first (`loadPlan`). Keep the periods in `ui-context.md`.
- **Model output and user text go in with `textContent`, never `innerHTML`** (comment at the chat code; `test_e2e.py::test_asking_the_plant_a_question`). `innerHTML` is allowed only for the static `ICONS` and the facts list built from `/api/site` constants. If a `/api/site` field ever holds free text, switch it to `textContent`.
- Show API numbers as they are. Use `tween(el, to, fmt, exact)` and pass `exact` when the text must equal the API value. Do not recompute in the browser what the API already gives.
- Times: use the API `label`, or `clock(iso)` with `state.site.timezone`. Never `toLocaleTimeString()` without `timeZone`.
- A failed fetch must show on the page ("Can't reach the plant") and keep the last good data. New JS motion checks `calm`. Browser storage: only `sessionStorage` for the chat id, inside `try/catch`.

## Testing

- Run `.venv/bin/python -m pytest -m "not e2e"` (268 tests, about 3 s). CI runs all 276 with `pytest --cov=backend --cov=simulation --cov-report=term-missing --cov-fail-under=40`, then two standalone proofs. The 8 browser tests need `playwright install chromium`.
- Tests go in `tests/`, in `test_<module or topic>.py`. `pytest.ini` sets `testpaths = tests`, `python_files = test_*.py`, `python_classes = Test*`, `python_functions = test_*` and `pythonpath = backend simulation automation/evals`. Import modules by bare name (`import brain`). There is no `__init__.py`.
- Never add tests to `backend/test_*.py` or `simulation/test*.py`. They are legacy runners that execute on import and are not collected (`pytest.ini` comment).
- Start each file with a docstring that says what it covers and why. A regression file names the bug ("Regression tests for bug #18").
- Group by behaviour in `class TestXxx` (`test_brain.py`), or use plain functions when a file tells one story (`test_acceptance.py`, `test_site_time.py`, `test_e2e.py`).
- **Name a test after the behaviour, as a sentence:** `test_a_failed_refresh_keeps_the_last_real_forecast`, `test_never_drains_below_the_reserve`. Do not name it after the function. Older tests are shorter (`test_returns_48_hours`).
- **Every fixed defect gets a regression test named after the behaviour,** with the bug number in a docstring or comment, in the same commit as the fix.
- Use the factory-fixture pattern from `conftest.py`: `make_solar`, `make_battery`, `make_device`, `make_input` return a builder function with defaults. Override only the fields the test is about. `make_input` is built on `make_solar` and `make_battery`. Add a `make_*` fixture for a new model with many fields. File-local helpers are plain functions (`weather_hours`, `plan`, `ask`).
- `mock_network` replaces `prices.fetch_market`, `weather.fetch_forecast`, `weather.fetch_real_forecast` (label `"test forecast"`) and the geocoding calls. `client` is `mock_network` plus no DB insert plus `TestClient(main.app)` as a context manager (this runs the lifespan). `live_server` runs the real app in a thread (`loop="asyncio", http="h11"`).
- Patch with `monkeypatch.setattr(module, "name", value)`; `unittest.mock` is not used. `main` keeps global state between tests, so patch `main.forecast_cache` and similar through `monkeypatch`, never by plain assignment.
- There is no pytest-asyncio. Run an async function in its own thread with `asyncio.run` (`test_weather.py::TestLivePlantWithoutWeather._refresh`), because the browser tests leave a loop running in the main thread (`7e48473`).
- **Acceptance tests check outcomes, not implementation.** They drive `energy_manager.decide` with real physics (`engine._apply_battery`) over two days that differ in one thing, then assert money, kWh and SoC bounds with a margin and a message that shows the numbers (`assert sunny < cloudy - 30, f"sunny {sunny:.0f} kWh ..."`).
- Use `@pytest.mark.parametrize` to run one check over many inputs, include the boundary values (`soc` 5, 10, 15) and add `ids=` when the values are not self-explanatory. Use `pytest.approx` for floats.
- Browser tests carry `@pytest.mark.e2e` (registered in `pytest.ini`). Keep them few. Check pixels, not only "visible" (the chart test counts battery-line pixels).
- Coverage: the CI gate is 40 %. The measured value on 2026-10-18 is 66 % (non-browser run; the legacy runners count as 0 %). Do not lower the gate. Do not treat 40 as a target: new code needs tests anyway.
- The proofs `simulation/verify_simulation.py` and `test_decisions.py` print PASS / FAIL but exit 0 on a failed check. After you change `engine.py`, `optimizer.py` or `factory.py`, run both (`cd simulation && python verify_simulation.py && python test_decisions.py`) and read the output for FAIL.
- When you add or remove tests, update the counts in `README.md` ("276 pytest tests") and `architecture-context.md` (Testing Model).

## Defects and Docs

**`docs/BUGS.md` workflow:**
1. A failing test or a review finds a defect. Open a GitHub issue with the repro steps.
2. Add a row at the TOP of the table ("Newest first"): `[#N](issue url)`, severity, area (file), one plain sentence on what was wrong, how it was found plus the regression test name, status, fix. Update the counts in the "Status:" paragraph.
3. Fix the root cause. Add the regression test in the same commit.
4. Set the row to "✅ Fixed" and give the commit hash or PR number. For an eval-found defect use "🔧 Fixed, re-run pending" until the eval is re-run.
5. Close the issue (`closes #N` / `fixes #N` in the commit or PR).

Severity: **Critical** (crashes or disables the app), **High** (crash on an edge input), **Medium** (wrong output or metric, app keeps running), **Low** (cosmetic). Old rows are `B-01` to `B-06`; new ones use the issue number. In history the row often lands in a follow-up commit ("Defect log: add #15") after the fix. That is fine; do not skip the row (#39 has none yet).

**Keeping docs honest:**
- The code wins when code and docs disagree (`project-overview.md`, Open Question 6). Fix the doc.
- The README must not state a measured result from a simulation. Label simulated numbers as simulated and name the script (README "What it saves, honestly", "Known limitations"). When a number changes (savings, test count), change README, `project-overview.md` and `architecture-context.md` together.
- Change a context file in the same change as the code it describes: modules, routes and constants in `architecture-context.md`; the page in `ui-context.md`; scope in `project-overview.md`; rules in this file. (`ai-workflow-rules.md` says the same in general terms.) `progress-tracker.md` does not exist yet; see `_handoff-for-progress-tracker.md`.
- Update a docstring when you change the function. Stale ones exist (see Inconsistencies).
- `docs/DESIGN.md` is history. Its "Principles" are a TARGET, not the present: see Inconsistencies.

## Git and Pull Requests

From `git log --oneline -70` and `git branch -a`. This describes what the history shows; it is not a stated policy.
- `main` is the default branch. Since PR #27 every change reaches it through a branch and a GitHub pull request (merge commits `Merge pull request #N from karimtataa46/<branch>`: #27, #30, #36, #37, #40). One unit of work per PR, a few commits each.
- Branch names are lower-case kebab-case: `m6-p2-hourly-decisions` (milestone and part), `m5-ai-agents`, `fix-real-weather-only`, `honest-savings-and-redesign`. Use `fix-<what>` for a defect. Only the oldest branch has a slash (`feature/facility-config`).
- A commit subject is one sentence in sentence case, with no final period, and no type prefix: "Never plan with made-up weather (fixes #39)", "Hourly market prices drive the plan and the live decisions (closes #32)". Prefixes seen: `Fix:` for a defect fix, `Tests:`, `Docs:`, `README:`, `Eval:`, `Defect log: add #N`. The `T1:` to `T5:` and `Step N:` labels appear only in early commits.
- Reference issues at the end of the subject: `(closes #N)`, `(fixes #N)`, `(#N)`, `(part of #N)`.
- For a non-trivial change write a body: first why (what went wrong, with the real symptom), then bullets of what changed, then the tests added. Plain sentences, wrapped at about 75 characters.
- A PR title is a short description of the unit of work (#37: "M6 step 2: hourly market prices drive the plan and the live decisions").
- Commits made with Claude end with the attribution trailer the session gives (`Co-Authored-By: Claude ... <noreply@anthropic.com>`, as in the history).
- CI must pass: `.github/workflows/tests.yml` runs on every push and pull request to `main`. The README badge shows the result.
- Never commit what `.gitignore` lists: `data/*.db`, `.venv`, `.coverage`, `.claude/`, `automation/evals/results/`, `automation/briefings/*.md`. `context/` is untracked today (`?? context/`); ask the owner before you add it.

## File Organization

| Kind of code | Goes in |
|--------------|---------|
| Live behaviour: route, loop, feed, storage | `backend/<noun>.py`, wired in `main.py`, tested in `tests/test_<noun>.py` |
| Decision logic | `backend/` beside `planner.py` and `brain.py`, with no I/O |
| Physics, tariffs, facility constants, the LP | `simulation/` (never battery physics in `backend/`) |
| Demo plant constants | `backend/simulator.py` (`DEMO_*`); core defaults in `simulation/factory.py`. Do not start a third place |
| The page | `frontend/index.html` (the only file) |
| n8n workflows, evaluation, dev fakes | `automation/workflows/`, `automation/evals/`, `automation/dev/` |
| Tests | `tests/` only |
| Defect log, design notes | `docs/` |
| Context for agents | `context/` |
| Runtime data | `data/` (created at run time, git-ignored) |

- File names are `lower_snake.py`. Standalone demos and proofs live in `simulation/`; give a new one an `if __name__ == "__main__":` guard (`demo_dynamic_pricing.py` and `test1_profile.py` to `test5_optimal.py` have it; `verify_simulation.py`, `test_decisions.py`, `stress_test.py`, `debug_lp.py` do not).
- Module list and dormant code: `architecture-context.md`, System Boundaries.
- **How imports work.** `backend/` imports `simulation/` modules as top-level names. Four mechanisms: `sys.path` edits in 7 backend modules; `pytest.ini` `pythonpath`; Docker `WORKDIR /app/backend`; and the import order in `main.py` (`weather_module` and `sim_module` come before `energy_manager` and `from engine import`).
- **Known fragility (verified 2026-10-18):** `import planner` or `import energy_manager` alone, run from `backend/`, fails with `ModuleNotFoundError: No module named 'engine'`. `import main` works.
- Rules:
  - Run the app from `backend/` (`cd backend && uvicorn main:app`, `start.sh`, Docker). Run tests from the repo root.
  - A new backend module that imports from `simulation/` either is imported by `main.py` after `weather` / `simulator`, or carries the guarded `sys.path` block of `weather.py` (copy that one, not `savings.py`'s).
  - Do not reorder the import lines in `main.py`. The order is silent: nothing explains it.
  - Build file paths from `Path(__file__)` (`../frontend`, `../simulation`, `../data`), never from the working directory.
  - The Docker image copies only `backend/`, `frontend/`, `simulation/`. Anything needed at run time must live there.
  - Do not turn folders into packages or remove the `sys.path` edits as a side effect. That is a planned, separate refactor (`DESIGN.md` R1).

## Inconsistencies

Do not "fix" these inside other work. If you want to fix one, make it its own change, with the owner's agreement.

1. **`sys.path`:** 7 backend modules edit it; 6 guard with `if ... not in sys.path`, `savings.py` does not. `planner.py`, `energy_manager.py` and `main.py` do not edit it. `backend/test_livesim.py` edits it too.
2. **Type hints:** `typing.List/Optional` in most files; built-in `list[...]` in `weather.py` and `database.py`. Implicit optionals (`start_soc_kwh: float = None`, `forecast: List[...] = None` in `engine.simulate`). `engine._apply_battery -> (float, float)` uses a tuple, not a type. Many helpers have no return type (`band_limits`, `price_bands`, `get_current_solar`, `fetch_real_forecast`).
3. **`models.py`:** the only file with `from __future__ import annotations` and the only one without a module docstring. It and `brain.py` keep old markers ("NEW:", "MODIFIED:").
4. **`main.py` imports:** `datetime` is imported twice (lines 11 and 38); `import os` is unused; groups are mixed; `price_book` is defined after `lifespan`, which uses it (works, because it is looked up at call time).
5. **Handler names:** `get_live`, `get_history` (older) against `api_plan`, `api_site` (newer).
6. **Error shapes:** real status plus `{"error"}` (`/api/ask`); HTTP 200 plus `{"error"}` (dormant routes); `available: false` (`/api/plan`); Pydantic `{"detail"}`.
7. **Loops and locks:** `/api/history` runs SQLite on the event loop. The whole tick runs on the loop. `_forecast_refresh_loop` has no `try/except`. `_refresh_forecast` sets `forecast_error` outside the lock on failure. Only two variables have a lock.
8. **Reason sentences:** `brain.decide` rules 1 to 6 write "12kW" and "0.28€" and use em dashes; `planner.py` and `_follow_plan` write "12 kW" and "€0.28" and use none.
9. **Magic numbers:** the 0.5 kW noise threshold and `1e-6` are inline; `planner._explain` uses a bare `5` where `SUN_CREDIT_KWH` exists; `models.BatteryState.is_full` / `is_critical` hard-code 95 and 15 (same values as `brain.py`, but `is_critical` is `< 15` while rule 1 uses `<= 15`); `simulator.get_solar` repeats `556 * 0.18` from `weather.py`.
10. **Scattered facts:** battery limits in `factory.py`, `simulator.py`, `brain.py`, `models.py`, `main.py`; tariffs 0.28 / 0.12 in `factory.py` and `simulator.py`; location in `weather.py`, `factory.py`, `simulator.py`, `prices.py`; load profile in `simulator.ZONES` and `factory.LOAD_PROFILE_KW` (different).
11. **SoC units:** percent against fraction (see Units). `engine.StepState.soc_pct` holds a fraction.
12. **Time constants:** `_S` (`assistant.py`) against `_SECONDS` / `_MINUTES` / `_HOURS`.
13. **Dates:** `savings.month_to_date` and `weather.fetch_dwd` use the UTC date; `PriceBook.refresh` uses the plant-local date; `prices.simulated_market` follows UTC hours.
14. **Frozen dataclasses:** only `HourPrice`.
15. **Stale text:** `weather.py` docstring ("Falls back to synthetic data if offline"; no longer true for the live path); `brain.py` header ("never go below 10%", old priority list; real values 15 / 20). Several tests carry old phase labels (`T1`, `T3`).
16. **Test style:** some tests import inside the function (`test_weather.py::TestRealForecastOnly`), most import at the top. Older tests are named by function, newer by behaviour.
17. **Legacy runners:** `backend/test_energy_logic.py`, `backend/test_livesim.py`, `simulation/test1..5`, `stress_test.py`, `debug_lp.py` are named like tests but are not pytest tests. Six run on import with no `__main__` guard. They count as 0 % in coverage.
18. **CI:** the proofs exit 0 on failure. The coverage gate (40 %) is far under the real value (66 %).
19. **Defect IDs:** `B-01..B-06` against `#N`. Branch `feature/facility-config` against flat names. `docs/BUGS.md` has no #39.
20. **Docs against files:** `context/CLAUDE.md` names `architecture.md` (the file is `architecture-context.md`) and `progress-tracker.md` (absent). `context/AGENTS.md` and `ai-workflow-rules.md` describe a Next.js / shadcn project. README's "without Docker" command (`uvicorn main:app --port 8000`) lacks the `--loop asyncio --http h11` flags every other start command uses.
21. **`DESIGN.md` Principles (a target) against the code:**
    - "One way to do each thing": not met (four simulators, two solar scales, scattered battery limits).
    - "`web -> api -> core`, core never imports web": half met. `simulation/` imports nothing from `backend/` and has no FastAPI, `urllib` or SQLite (checked). The `web/`, `api/`, `core/` folders do not exist and nothing is a package.
    - "No `sys.path` hacks" (R1): not done; there are 7, not the 6 it counts.
    - "Never break green": met by CI; its "152 checks" is now 276 tests.
