# ⚡ myEnergy

[![tests](https://github.com/karimtataa46/myenergy/actions/workflows/tests.yml/badge.svg)](https://github.com/karimtataa46/myenergy/actions/workflows/tests.yml)

**Predictive energy management for factories with solar and battery storage.**

myEnergy reads a facility's solar inverter, battery and grid meter and decides, every
few seconds, when to charge, discharge, hold, or draw from the grid. Unlike a normal
reactive controller, it is predictive: it reads the weather and price forecast and
plans ahead, so it stores cheap energy before an expensive peak instead of reacting
once the peak has already arrived.

On a simulated mid-sized factory it cuts the electricity bill by roughly €740 per
month compared with a standard reactive controller running the exact same hardware,
and by more under dynamic (spot) pricing, where the optimiser pulls further ahead of
any hand written rules.

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
| **Savings** | What is it saving? This month, the projected month and CO2 avoided, estimated against a plain controller on the same hardware. |
| **Your system** | What is my plant? Location, solar and battery size, reserve, prices and the devices it controls. |

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
  savings.py         month to date savings via the validated engine
  database.py        SQLite history
simulation/        the validated, tested core
  factory.py         facility model, tariffs, price series
  engine.py          energy balance physics
  optimizer.py       Model Predictive Control via linear programming (SciPy)
  controllers.py     reactive and predictive controllers
  test_*.py          the test suites
automation/        AI agents on top of the API (n8n + LLM)
  workflows/         the n8n workflows, versioned as JSON
  evals/             the agent's evaluation set and runner
```

### The decision engine

The decision engine is the product; the simulation just gives it a realistic world to
act in. Two strategies run on identical hardware, so the difference between them is a
fair measure of the software's value:

* **Reactive controller** (the baseline): responds only to the current moment.
* **Predictive optimiser** (Model Predictive Control): each step it solves a linear
  program over a rolling forecast horizon (the cheapest way to charge and discharge
  given the coming solar and prices), applies only the first action, then re solves on
  the next step with fresh data.

Savings are always reported as the gap between smart and plain control of the same
hardware, never as an absolute number that the solar panels would have produced anyway.

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

**252 automated checks** (201 pytest, plus 39 engine and 12 optimiser proofs), with a
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
