"""
Where this month's savings come from, on the real hourly prices.

The plant's bill is built up in layers, each estimated with the same validated
simulation engine (simulation/engine.py):

  without anything        the factory buys every kWh from the grid
  + solar panels          the panels cover part of the load
  + battery, price rule   a hand-written rule with no forecast: store surplus solar,
                          fill the battery in the cheapest third of the day's hours,
                          use it in the dearest third
  + myEnergy              the optimiser the live system runs, steering by a solar
                          forecast that is off by about 15% (real forecasts never are
                          perfect) and the published day-ahead prices

Only the last layer is what the software adds. The panels and a simple price rule
save money without it, so they are reported separately instead of being counted as
myEnergy's saving.

Prices are the real German day-ahead prices (prices.py) for the days in question:
this month so far, and the last 30 days for a full month. The weather is simulated,
so the result is an estimate, not a measurement of a real plant.
"""

import sys
import os
import calendar
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from typing import List, Optional

# Make the simulation package importable from the backend
_SIM_DIR = os.path.join(os.path.dirname(__file__), "..", "simulation")
sys.path.insert(0, os.path.abspath(_SIM_DIR))

import factory as F           # noqa: E402
import prices                  # noqa: E402
from engine import simulate   # noqa: E402
from controllers import price_rule  # noqa: E402
from optimizer import optimal  # noqa: E402
from simulator import DEMO_CFG                 # noqa: E402  the same plant as the live demo

FORECAST_ERROR = 0.15          # how far off the solar forecast's daily cloud cover is, on average


def _idle(state) -> float:
    return 0.0


def layers(days: int, buy: Optional[List[float]] = None, sell: Optional[List[float]] = None,
           forecast_error: float = FORECAST_ERROR) -> dict:
    """The bill and what each layer saves over `days` simulated days at these hourly prices."""
    days = max(days, 1)
    weather = F.generate_month_weather(days=days, seed=42)
    run = dict(cfg=DEMO_CFG, buy_price=buy, sell_price=sell)
    grid_only = simulate(weather, _idle, **{**run, "cfg": replace(DEMO_CFG, solar_peak_kw=0.0)})
    solar = simulate(weather, _idle, **run)
    with_rule = simulate(weather, price_rule, **run)
    myenergy = simulate(weather, optimal, forecast=F.forecast_of(weather, error=forecast_error), **run)
    by_myenergy = with_rule.cost_eur - myenergy.cost_eur
    return {
        "bill_without_anything_eur": round(grid_only.cost_eur, 2),
        "bill_eur": round(myenergy.cost_eur, 2),
        "saved_by_solar_eur": round(grid_only.cost_eur - solar.cost_eur, 2),
        "saved_by_battery_rule_eur": round(solar.cost_eur - with_rule.cost_eur, 2),
        "saved_by_myenergy_eur": round(by_myenergy, 2),
        "myenergy_pct_of_bill": round(by_myenergy / with_rule.cost_eur * 100, 1) if with_rule.cost_eur else 0,
        "co2_avoided_kg": round(grid_only.co2_kg - myenergy.co2_kg, 1),
    }


_cache: dict = {}


def _period(first: date, days: int) -> tuple:
    """Layers for `days` days from `first` on those days' real prices. Results on real
    prices are kept; a fallback to simulated prices (the price service didn't answer)
    is not, so the next request tries the real prices again."""
    key = (first, days)
    if key in _cache:
        return _cache[key]
    buy, sell, source = prices.daily_prices(first, days)
    result = (tuple(layers(days, buy, sell).items()), source)
    if source == prices.SOURCE_REAL:
        if len(_cache) > 16:
            _cache.clear()
        _cache[key] = result
    return result


def month_to_date(now: Optional[datetime] = None) -> dict:
    """This month so far (day 1 to today) and a full 30-day month (the last 30 days)."""
    now = now or datetime.now(timezone.utc)
    today = now.astimezone(prices.SITE_TZ).date()
    so_far, source = _period(today.replace(day=1), today.day)
    full, full_source = _period(today - timedelta(days=30), 30)
    return {
        "month": today.strftime("%B %Y"),
        "days_elapsed": today.day,
        # Real length of THIS month (28/29/30/31) so the progress bar is correct.
        "days_in_month": calendar.monthrange(today.year, today.month)[1],
        "so_far": dict(so_far),
        "full_month": dict(full),
        "forecast_error_pct": round(FORECAST_ERROR * 100),
        "weather": "simulated",
        "prices": "real" if source == full_source == prices.SOURCE_REAL else "simulated",
        "price_source": source,
    }
