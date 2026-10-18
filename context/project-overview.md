# myEnergy

## Overview

myEnergy is a predictive energy-management prototype for a factory with solar panels, a battery and a grid connection. Every 5 seconds it decides whether the battery charges, discharges or holds. The aim is to buy as little grid power as possible, and as cheap as possible, without running short. It does not only react to the present. It plans 36 hours ahead from the weather forecast, the expected load and hourly prices, applies only the current hour, and plans again at the next tick. The factory is simulated (Munich, 250 kWp solar, 200 kWh / 50 kW battery, about 90 kW daytime load); there is no real hardware. The owner builds it as a learning and CV/portfolio prototype, not as a commercial product. The imagined user is the operator of a mid-sized factory.

## Goals

1. Decide every 5 seconds: charge, discharge or hold the battery, and give a one-sentence reason.
2. Plan 36 hours ahead with a linear program (SciPy, HiGHS), re-planned every tick (Model Predictive Control).
3. Plan only with real data: the Open-Meteo forecast (then the German weather service DWD via Bright Sky) and real German day-ahead prices (Energy-Charts) plus a 0.10 EUR/kWh surcharge. With no forecast, run on fallback rules.
4. Keep the plant safe: safety rules always override the plan.
5. Show the operator, on one page, what the plant does, what it plans and why, in plain language.
6. Report savings honestly in layers, so the software is credited only for what it adds.
7. Let the operator ask questions in German or English, answered from live data by a read-only AI assistant that is never part of the control path.

## The Core Decision

The owner's words: "It is cloudy now and I need the battery later. Should I buy grid power, or will the sun be back in two hours, so I can use the battery now and let the sun refill it for free?"

A plain controller sees "cloudy, battery low" and buys. myEnergy reads the forecast for the next 36 hours. If the sun returns, it uses the battery now and lets the sun refill it. If it does not, it buys, in the cheapest hours it can find.

Worked example, measured by running the planner offline (demo plant, 10:00 local, battery 40%, day/night tariff 0.28 EUR/kWh by day and 0.12 at night). In both cases the battery discharges 38 kW now, because it is the cheapest source. The difference comes later:

| | Sun back after 2 hours | Cloudy all the time |
|---|---|---|
| How the battery refills | 158 kWh of free solar, full (95%) by about 18:00 | no solar reaches it; full by about 07:00 on night-rate grid power |
| Grid energy bought for the battery, next 24 h | **81 kWh** | **158 kWh** |

The sun saves about 77 kWh of buying. `tests/test_acceptance.py` checks the same behaviour.

The software minimises **cost**, not grid kWh. The two usually agree, but not always: it may buy extra cheap night power, store it and use it in dear hours. That can raise the grid kWh and still lower the bill. The planner has no term for grid kWh or CO2.

## Core User Flow

1. Open the page at `/`. The status pill says "Running normally", "Readings delayed", "No forecast: running on safe rules" or "Can't reach the plant".
2. **Right now:** read what the plant is doing and why (one sentence), with solar, factory load, battery %, grid in or out, the grid price (cheap, average or expensive hour) and the solar share of the last hour.
3. **Tonight and tomorrow:** read the plan's headline (for example "Waiting for the sun"), the grid energy bought for the battery, the free solar stored, and the 36-hour chart.
4. **Savings:** read this month so far, or a full month, split into solar panels, battery on a simple timer, myEnergy's planning and the bill still paid.
5. **Your system:** look up location, solar and battery size, reserve, tariff, price source and the controlled devices.
6. Optionally, open "Ask your plant" and ask in plain words. The page is read-only: nothing on it changes the plant.

## Features
### Live control loop
- `backend/main.py` runs a tick every 5 s: read the plant, build the forecast, decide, apply, save to SQLite (last 24 h), publish at `/api/live`.
- Weather and prices refresh every 30 min; if a refresh fails, the last real forecast is kept. Every decision carries a one-sentence reason that must match the real power flow.

Status: Built on a simulated plant.

### Forecast planning
- The LP finds the cheapest battery schedule over 36 hourly slots from forecast solar, expected load (a fixed profile: about 90 kW by day, 27 kW at night) and hourly prices.
- Weather is real only. With no real forecast the plan view says so and the rules decide.
- Prices are German day-ahead market prices. Hours not yet published are estimated from the same hour a day earlier. If prices cannot be fetched, a simulated price model is used and "Your system" says so.

Status: Built on a simulated plant.

### Safety rules
- Battery never below the 20% reserve, never charged above 95%, never discharged into the grid.
- A 95 kW demand ceiling limits battery charging and optional grid-powered devices. A device forced by its deadline may exceed it.
- A plan that counted on sun never turns into buying peak-price power when the sun falls short.

Status: Built on a simulated plant.

### Flexible devices
- Two simulated devices: Delivery Van EV (11 kW, 40 kWh, due 12 h after server start) and Industrial Water Heater (15 kW, 10 kWh, due after 4 h, not interruptible once started).
- Rules switch them on when the deadline forces it, when free solar covers them, or in a cheap price hour. Minimum on and off times protect the equipment.
- Limits: the battery plan does not include them, and each device has one job per server start (once done, it stays done until a restart).

Status: Built on a simulated plant.

### Operator interface
- One page, `frontend/index.html` (plain HTML, CSS and JavaScript): Right now, Tonight and tomorrow, Savings, Your system.
- It polls the API (live 5 s, plan 60 s, savings 5 min) and shows when data is missing or late. It is read-only and adapts to a phone screen.

Status: Built.

### Savings reporting
- Layers: panels, battery on a timer, myEnergy's planning. Only the last is the software's.
- Figures from the README, on one **simulated**, summer-like month (250 kWp, 200 kWh, day/night tariff, each day's cloud cover shifted by a random error with standard deviation 0.15): solar about EUR 7,100/month, battery on a timer about EUR 1,080, myEnergy's planning about EUR 40 (EUR 110 with a perfect forecast). A full year would save clearly less. With hourly prices the optimiser beats a simple price-threshold rule by about EUR 270 a month (`simulation/demo_dynamic_pricing.py`, re-run on 2026-10-18: EUR 266), but that script uses simulated prices, the default 100 kWp factory and a perfect forecast, so it is an upper bound. The old README claim of about EUR 740/month was wrong: it credited the night tariff and a perfect forecast to the software.

Status: Built on a simulated plant. The figures are simulated, not measured.

### AI assistant
- "Ask your plant": an n8n chat agent with an LLM (Gemini by default; Claude possible). It reads four endpoints (live, plan, savings, site), answers in German or English, and cannot change anything.
- The browser talks only to myEnergy (`POST /api/ask`): 5 questions a minute per visitor, 500 characters each. The button is hidden when no agent is configured, as on the public demo.
- A second workflow writes a short German briefing at 06:30 (Europe/Berlin). A 20-question evaluation grades answers against the API.

Status: Built on a simulated plant. A clean full evaluation re-run is still pending (`automation/README.md`).

### Simulation and validation
- `simulation/` holds the validated physics (energy balance, battery limits, efficiency), the facility profile, the controllers and the LP optimiser.
- The live simulated plant takes its solar from the same real forecast the planner uses, so live planning never meets a forecast miss. Forecast error appears only in the savings month (15%).
- A pytest suite (unit, API, browser E2E, workflow checks) runs in CI on every push and never reaches the internet. Defects are logged in `docs/BUGS.md`.

Status: Built.

### Developer APIs
- Used by the page or the agent: `/api/live`, `/api/plan`, `/api/savings`, `/api/site`, `/api/assistant`, `/api/ask`. Also available, but no page or agent calls them: `/api/history`, `/api/forecast`, `/api/prices`.
- `/api/estimate`, `/api/cities`, `/api/facility/*` and `/api/sim/*`, with `estimate_service.py`, `pricing_service.py`, `facility_live.py` and `live_sim.py` (about 800 lines), served pages that were removed. They are still tested and shipped.

Status: Dormant for the second group. The rest is Built.

## Scope
### In Scope
- One simulated plant (Munich) with a battery and two flexible devices.
- Battery decisions every 5 s from a 36-hour plan, inside the safety rules, with rule-based fallback, using real weather and real German day-ahead prices.
- A read-only operator page, a read-only AI assistant and a daily briefing. Layered savings estimates on a simulated month.
- Tests, CI, Docker, Docker Compose (with n8n) and a Render config.

### Out Of Scope
- Real inverter, battery or meter integration: out of scope for now; see Open Questions.
- More than one plant or site: state lives in one process, for one plant.
- User accounts and authentication: the API has none, and CORS allows every origin.
- Billing, mobile apps and machine-learning forecasts (the page works in a phone browser; weather comes from Open-Meteo or DWD and load is a fixed profile).
- Letting the assistant switch devices or change settings.
- Measured savings: there is no real plant, and actual savings are not stored.

## Success Criteria

1. Before a sunny day it buys clearly less overnight (more than 30 kWh less) than before a cloudy day, also on the demo plant: `tests/test_acceptance.py`.
2. With a forecast it costs less than the same engine without one, buys battery energy only in cheap hours and never drops below the 20% reserve: `tests/test_acceptance.py`, `tests/test_brain.py`.
3. It never plans with made-up weather. Without a real forecast the page says "No forecast: running on safe rules": `tests/test_weather.py`, `tests/test_e2e.py`.
4. The reason sentence matches the real power flow: `tests/test_brain.py` (`test_the_sentence_matches_the_actual_power_flow`).
5. Savings are layers, and the software is credited only for the gap to a battery on a timer: `tests/test_savings.py`.
6. A 36-hour plan is solved well inside the 5-second tick (about 0.5 ms when measured for this file; no test enforces it).
7. The assistant's answers are graded against the API's numbers, and the grader is itself tested: `tests/test_eval_grading.py`.

## Open Questions

1. Optimisation objective: lowest cost (today), least grid kWh, or lowest CO2?
2. Is "battery full by a given time" a hard requirement? If so, which time and level? Today nothing guarantees a charge level at a given time.
3. Real hardware target (which inverter, which protocol), or simulator only?
4. The dormant subsystems: delete them, or keep them as onboarding?
5. Savings realism: the simulated month has one cloud value per day and is summer-like, so "cloudy now, sunny in two hours" never happens inside it. The figures are likely optimistic for a full year. The page also labels them with the real calendar month.
6. Docs and code disagree in these places (the code wins). The README was corrected on 2026-10-18 and now matches the code, including a "Known limitations" section.
   - The savings use a fixed day/night tariff (0.28 / 0.12 EUR/kWh, `simulator.py`), but the live plan uses hourly market prices.
   - `docs/DESIGN.md` is outdated (four pages, "two brains"). `docs/BUGS.md` lacks #39. The `weather.py` header still says it falls back to synthetic data. `context/AGENTS.md` and `context/ai-workflow-rules.md` describe a Next.js / shadcn project; this one is Python/FastAPI with one HTML page.
   - Technical findings (for example solar calibration) are in `context/architecture-context.md`.
