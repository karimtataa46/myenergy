# ⚡ myEnergy

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

| Surface | What it shows |
|---------|---------------|
| `/` | Live dashboard for a simulated factory: self powered %, battery / solar / grid state, month to date savings, the current decision, power flow and forecast. |
| `/estimate` | Enter your own site (city, solar kWp, battery kWh, monthly usage) and get a predictive savings estimate plus a live dashboard for that facility. |
| `/sim` | Accelerated savings session: runs the optimiser against a plain baseline in fast forward and banks the gap second by second. |

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


## Run it without Docker

```bash
pip install -r requirements.txt
cd backend
uvicorn main:app --port 8000
```

## Tests

The decision making is verified, not assumed:

```bash
cd simulation && python3 verify_simulation.py   # physics and hand computed answers
cd simulation && python3 test_decisions.py      # optimiser vs an independent brute force search
cd backend    && python3 test_energy_logic.py   # demand cap, arbitrage gate, device rules
cd backend    && python3 test_livesim.py        # the /sim engine input and output
```

## Tech stack

Python, FastAPI, Docker, SciPy (linear programming), SQLite, Open-Meteo, vanilla JavaScript.
