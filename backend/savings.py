"""
Where this month's savings come from.

The plant's bill is built up in layers, each estimated with the same validated
simulation engine (simulation/engine.py) over a simulated month of weather:

  without anything     the factory buys every kWh from the grid
  + solar panels       the panels cover part of the load
  + battery on a timer a cheap timer: store surplus solar, fill the battery every
                       night at the cheap rate, use it by day (no forecast)
  + myEnergy           the optimiser the live system runs, steering by a forecast
                       that is off by about 15% (real forecasts are never perfect)

Only the last layer is what the software adds. The panels and the night-tariff
trick save money without it, so they are reported separately instead of being
counted as myEnergy's saving. (An earlier version compared myEnergy with a
controller that never charged at night, which credited the night tariff to the
software.)
"""

import sys
import os
import calendar
from dataclasses import replace
from datetime import datetime, timezone
from functools import lru_cache

# Make the simulation package importable from the backend
_SIM_DIR = os.path.join(os.path.dirname(__file__), "..", "simulation")
sys.path.insert(0, os.path.abspath(_SIM_DIR))

import factory as F           # noqa: E402
from engine import simulate   # noqa: E402
from controllers import timer  # noqa: E402
from optimizer import optimal  # noqa: E402
from simulator import DEMO_CFG                 # noqa: E402  the same plant as the live demo

FORECAST_ERROR = 0.15          # how far off the forecast's daily cloud cover is, on average


def _idle(state) -> float:
    return 0.0


def layers(days: int, forecast_error: float = FORECAST_ERROR) -> dict:
    """The bill and what each layer saves over `days` simulated days."""
    days = max(days, 1)
    weather = F.generate_month_weather(days=days, seed=42)
    grid_only = simulate(weather, _idle, cfg=replace(DEMO_CFG, solar_peak_kw=0.0))
    solar = simulate(weather, _idle, cfg=DEMO_CFG)
    with_timer = simulate(weather, timer, cfg=DEMO_CFG)
    myenergy = simulate(weather, optimal, cfg=DEMO_CFG,
                        forecast=F.forecast_of(weather, error=forecast_error))
    by_myenergy = with_timer.cost_eur - myenergy.cost_eur
    return {
        "bill_without_anything_eur": round(grid_only.cost_eur, 2),
        "bill_eur": round(myenergy.cost_eur, 2),
        "saved_by_solar_eur": round(grid_only.cost_eur - solar.cost_eur, 2),
        "saved_by_battery_timer_eur": round(solar.cost_eur - with_timer.cost_eur, 2),
        "saved_by_myenergy_eur": round(by_myenergy, 2),
        "myenergy_pct_of_bill": round(by_myenergy / with_timer.cost_eur * 100, 1) if with_timer.cost_eur else 0,
        "co2_avoided_kg": round(grid_only.co2_kg - myenergy.co2_kg, 1),
    }


@lru_cache(maxsize=64)
def _cached(days: int) -> tuple:
    return tuple(layers(days).items())


def month_to_date() -> dict:
    """This month so far (days 1 to today) and a full 30-day month, layer by layer."""
    now = datetime.now(timezone.utc)
    return {
        "month": now.strftime("%B %Y"),
        "days_elapsed": now.day,
        # Real length of THIS month (28/29/30/31) so the progress bar is correct.
        "days_in_month": calendar.monthrange(now.year, now.month)[1],
        "so_far": dict(_cached(now.day)),
        "full_month": dict(_cached(30)),
        "forecast_error_pct": round(FORECAST_ERROR * 100),
        "weather": "simulated",
    }
