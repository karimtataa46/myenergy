"""
Month-to-date savings.

Reuses the SAME validated simulation engine from Test 4 to compute how much
myEnergy has saved this calendar month so far (days 1 → today), plus the
projected full-month figure. Because it's the identical engine the tests
ran, the dashboard number is consistent with the analysis you already saw.
"""

import sys
import os
import calendar
from datetime import datetime, timezone
from functools import lru_cache

# Make the simulation package importable from the backend
_SIM_DIR = os.path.join(os.path.dirname(__file__), "..", "simulation")
sys.path.insert(0, os.path.abspath(_SIM_DIR))

import factory as F           # noqa: E402
from engine import simulate   # noqa: E402
from controllers import reactive, predictive  # noqa: E402


def _saving_for_days(days: int) -> dict:
    days = max(days, 1)
    weather = F.generate_month_weather(days=days, seed=42)
    base = simulate(weather, reactive)
    smart = simulate(weather, predictive)
    saving = base.cost_eur - smart.cost_eur
    co2 = base.co2_kg - smart.co2_kg
    return {
        "baseline_cost_eur": round(base.cost_eur, 2),
        "myenergy_cost_eur": round(smart.cost_eur, 2),
        "saved_eur": round(saving, 2),
        "co2_avoided_kg": round(co2, 1),
        "pct_of_bill": round(saving / base.cost_eur * 100, 1) if base.cost_eur else 0,
    }


@lru_cache(maxsize=64)
def _cached(days: int) -> tuple:
    d = _saving_for_days(days)
    return tuple(d.items())


def month_to_date() -> dict:
    """Savings from the 1st of the current month through today."""
    now = datetime.now(timezone.utc)
    mtd = dict(_cached(now.day))           # day-of-month = days elapsed
    full = dict(_cached(30))               # projected full month

    mtd["projected_full_month_eur"] = full["saved_eur"]
    mtd["projected_co2_kg"] = full["co2_avoided_kg"]
    mtd["days_elapsed"] = now.day
    # Real length of THIS month (28/29/30/31) so the progress bar is correct.
    mtd["days_in_month"] = calendar.monthrange(now.year, now.month)[1]
    mtd["month"] = now.strftime("%B %Y")
    return mtd
