# ⚡ myEnergy

**Predictive energy management for factories with solar + battery.**

myEnergy connects to a facility's existing solar inverter, battery and grid meter
and decides — every few seconds — when to charge, discharge, hold or pull from the
grid. Unlike a normal *reactive* controller, it is *predictive*: it reads the
weather/price forecast and plans ahead, so it banks cheap energy before an expensive
peak instead of reacting once the peak has already hit.

On a simulated mid-sized factory it cuts the electricity bill by **~€740/month vs a
standard reactive controller on the exact same hardware** — and more under dynamic
(spot) pricing, where its optimiser pulls further ahead of any hand-written rules.

> Status: working **prototype**. The "facility" is a physically-realistic
> simulation, not yet real hardware — but the decision engine, optimiser and
> savings maths are all real and independently tested.

---

## What's inside

| Page | What it shows |
|------|---------------|
| `/` | WHOOP-style dashboard: live self-powered %, battery/solar/grid rings, month-to-date savings, AI decision, power-flow chart, forecast, zones |
| `/sim` | Live savings session — runs the optimiser vs a dumb baseline in accelerated real time and banks the gap per second |

## How it's built

```
frontend/        vanilla HTML/CSS/JS (no framework) — dashboard + live session
backend/         FastAPI server
  ├─ main.py        REST API + 5-second control loop
  ├─ brain.py       rule-based live decision engine
  ├─ live_sim.py    drives /sim with the LP optimiser
  ├─ simulator.py   fake facility hardware (solar/load/battery)
  ├─ weather.py     Open-Meteo forecast (no API key needed)
  ├─ savings.py     month-to-date savings via the validated engine
  └─ database.py    SQLite history
simulation/      the validated, tested core
  ├─ factory.py     factory model, tariffs, price series
  ├─ engine.py      energy-balance physics
  ├─ optimizer.py   Model-Predictive Control via linear programming (scipy)
  ├─ controllers.py reactive vs predictive controllers
  └─ test_*.py      tests (see below)
```

**The decision engine is the product.** The simulation just gives it a realistic
world to act in. Savings are always measured as the *gap* between smart and dumb
control of identical hardware — never an absolute number that the solar panels
would have produced anyway.

## Run it locally

```bash
git clone <your-repo-url> myenergy
cd myenergy
pip install -r requirements.txt
./start.sh                 # or:  cd backend && uvicorn main:app --port 8000
```

Then open **http://localhost:8000**.

## Tests

The decision-making is verified, not assumed:

```bash
cd simulation && python3 verify_simulation.py   # physics + hand-computed answers
cd simulation && python3 test_decisions.py      # optimiser vs an independent brute-force search
cd backend    && python3 test_livesim.py        # the /sim engine's I/O
```

## Deploy it (so it's not just localhost)

GitHub stores the code; it does **not** run the Python backend. To put it on a
public URL, deploy to a Python host. Easiest free option — **Render**:

1. Push this repo to GitHub.
2. On [render.com](https://render.com): **New → Blueprint**, pick the repo.
   Render reads `render.yaml` and deploys automatically.
3. You get a public `https://myenergy-xxxx.onrender.com` URL.

(The same `Procfile` also works on Railway / other Heroku-style hosts.)

## Tech

Python · FastAPI · SciPy (linear programming) · SQLite · Chart.js · Open-Meteo
