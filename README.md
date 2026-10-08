# ⚡ myEnergy

[![tests](https://github.com/karimtataa46/myenergy/actions/workflows/tests.yml/badge.svg)](https://github.com/karimtataa46/myenergy/actions/workflows/tests.yml)

**Predictive energy management for factories with solar and battery storage.**

myEnergy reads a facility's solar inverter, battery and grid meter and decides, every
few seconds, when to charge, discharge, hold, or draw from the grid. Unlike a normal
reactive controller, it is predictive: it reads the weather and price forecast and
plans ahead, so it stores cheap energy before an expensive peak instead of reacting
once the peak has already arrived.

**What it saves, honestly.** The demo factory (250 kWp solar, 200 kWh battery) pays the
real German day-ahead market price, which changes every hour, plus a fixed amount for
grid fees and taxes. On the last 30 days of real prices (as of 8 October 2026, with
simulated weather) one month breaks down like this:

| Layer | Saves per month |
|-------|-----------------|
| Solar panels | about €6,000 |
| Battery on a simple price rule (store solar, charge in the cheapest third of the day's hours, use it in the dearest) | about €960 |
| **myEnergy's planning**, with a solar forecast about 15% off and only published prices | **about €300** (4.7% of the bill) |

The panels and a simple price rule save money with any controller, so only the last
line is the software's. With a perfect forecast it would be about €520, with a poor one
(30% off) about €280. On a fixed day/night tariff the same comparison gives only about
€40, because a timer already gets most of the battery's value there: forecast-based
planning pays off when prices change every hour. The numbers move as the 30-day window
moves; the page shows the current ones.

An earlier version of this README claimed about €740 a month on the fixed tariff. That
compared the software with a controller that never charged at night, and let it see the
real future weather, so it credited the night tariff and a perfect forecast to the
software.

> **Status:** working prototype. The "facility" is a physically realistic simulation,
> not yet real hardware. The decision engine, the optimiser and the savings maths are
> all real and independently tested.

## What it does

One interface, at `/`, for the person who operates the plant. Its sections follow
the operator's questions, in order:

| Section | Answers |
|---------|---------|
| **Right now** | Is it working, and what is it doing? One sentence plus solar, consumption, battery and grid, with the current price. A status pill says if there's no forecast or the plant can't be reached. |
| **Tonight and tomorrow** | What will it do, and why? The plan's story, the grid energy bought tonight, the free solar stored, and the hour-by-hour timeline. |
| **Savings** | What is it saving, and which part is the software? The bill split into layers: solar panels, battery on a simple price rule, and myEnergy's planning, for this month so far and the last 30 days, on real market prices. |
| **Your system** | What is my plant? Location, solar and battery size, reserve, prices and the devices it controls. |
| **Ask your plant** | Anything else, in their own words. A corner button opens a chat with the AI assistant (below), which answers from the live data. It only appears when the assistant is running. |

All times are in the plant's local time. The simulated plant behind it is a
development tool: it lets the test suite prove the system works, and is not part
of the user's interface.

### AI agents (n8n + LLM)

On top of the API run two n8n workflows with a language model, Google Gemini (Claude
works too; details in [automation/README.md](automation/README.md)):

* **Frag deine Anlage**: a chat agent that answers the operator's questions in German or
  English by calling the myEnergy API as tools, with a system prompt that only allows
  answers grounded in the plant's real numbers.
* **Daily briefing**: every morning a short German briefing about today and tonight.
* **Evaluation**: one command asks the agent 20 questions and grades every answer against
  the API's numbers at that moment, including questions it must decline.

## How it works

The project is split into a validated simulation core and a web plus control layer
built on top of it.

```
frontend/          vanilla HTML, CSS and JS (no framework)
backend/           FastAPI server
  main.py            REST API and the 5 second control loop
  brain.py           rule based live decision engine
  live_sim.py        drives /sim with the LP optimiser
  simulator.py       simulated facility hardware (solar, load, battery)
  weather.py         Open-Meteo forecast (no API key needed)
  savings.py         this month's savings, layer by layer, via the validated engine
  database.py        SQLite history
simulation/        the validated, tested core
  factory.py         facility model, tariffs, price series
  engine.py          energy balance physics
  optimizer.py       Model Predictive Control via linear programming (SciPy)
  controllers.py     reactive, timer, price-rule and predictive controllers
  test_*.py          the test suites
automation/        AI agents on top of the API (n8n + LLM)
  workflows/         the n8n workflows, versioned as JSON
  evals/             the agent's evaluation set and runner
```

### The decision engine

The decision engine is the product; the simulation just gives it a realistic world to
act in. Strategies run on identical hardware, so the difference between them is a fair
measure of the software's value:

* **Reactive controller**: responds only to the current moment.
* **Price rule** (the fair baseline): charges the battery in the cheapest third of the
  day's hours and uses it in the dearest third, with no forecast.
* **Predictive optimiser** (Model Predictive Control): each step it solves a linear
  program over a rolling forecast horizon (the cheapest way to charge and discharge
  given the coming solar and prices), applies only the first action, then re solves on
  the next step with fresh data.

The software's saving is always reported as the gap between the optimiser and the price
rule on the same hardware and the same real prices, with the optimiser steering by an
imperfect solar forecast (`factory.forecast_of`) and only the prices published by then,
never as a number the solar panels or a simple rule would have produced anyway.

## Run it with Docker

The whole app is containerised, so it runs the same way on any machine that has Docker
installed.

```bash
docker build -t myenergy .
docker run -p 8000:8000 myenergy
```

To run it together with n8n and the AI agents, use Docker Compose:

```bash
docker compose up -d
```


## Run it without Docker

```bash
pip install -r requirements.txt
cd backend
uvicorn main:app --port 8000
```

## Testing

An automated test suite runs on every push via **GitHub Actions** (the badge above is
live). It covers the full test pyramid:

| Layer | What it checks | Tools |
|-------|----------------|-------|
| **Unit** | decision rules, engine physics, pricing, models, forecast maths | pytest, fixtures, `parametrize` |
| **Integration** | services wired together, Open-Meteo HTTP calls mocked | `monkeypatch` test doubles |
| **API** | every endpoint, happy paths and error / 422 paths | FastAPI `TestClient` |
| **E2E** | the operator interface in a real headless browser | Playwright |
| **AI agents** | the n8n workflows match the API, and the eval's grader passes good answers and fails bad ones | pytest |

**328 automated checks** (277 pytest, plus 39 engine and 12 optimiser proofs), with a
coverage gate enforced in CI. Every defect the suite finds is filed as an issue, fixed,
guarded by a regression test, and recorded in the [defect log](docs/BUGS.md).

Run it locally:

```bash
pip install -r requirements-dev.txt
playwright install chromium              # once, for the browser E2E tests
pytest                                   # run everything
pytest --cov=backend --cov=simulation    # with a coverage report
pytest -m "not e2e"                      # skip the slow browser tests
```

## Tech stack

Python, FastAPI, Docker and Docker Compose, SciPy (linear programming), SQLite, Open-Meteo,
vanilla JavaScript.

**AI and automation:** n8n (AI Agent, tools, memory, scheduled workflows), Google Gemini API,
prompt engineering, LLM evaluation.

**Testing and CI:** pytest, pytest-cov, FastAPI TestClient, Playwright, GitHub Actions.
