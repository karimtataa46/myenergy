"""
The single entry point the live system calls every tick to decide what to do.

    decide(inp, forecast, cfg) -> EnergyDecision

It takes the current readings (BrainInput) plus the hourly forecast for the
coming hours (PlanningForecast):

  1. The forecast planner (planner.py) plans the battery over the next 36 hours
     and says what to do this hour, e.g. "wait for the sun" or "buy now".
  2. brain.py schedules the flexible devices and applies that battery setpoint
     inside its safety envelope (reserve, full battery, demand cap).
  3. With no forecast, or if the solver fails, the rule engine in brain.py
     decides on its own, so the system always has a safe answer.
"""
from dataclasses import replace
from typing import Optional

import brain
import factory as F
import planner
from models import EnergyDecision, PlanningForecast


def plan_for(battery, forecast: Optional[PlanningForecast], cfg=None) -> Optional[planner.Plan]:
    """The plan the live system follows, within the brain's safety limits.
    Shared by decide() and the dashboard so both always show the same plan."""
    if forecast is None:
        return None
    return planner.make_plan(
        battery, forecast, cfg or F.DEFAULT_CONFIG,
        min_soc_frac=brain.BATTERY_RESERVE_SOC / 100.0,
        max_soc_frac=brain.BATTERY_FULL_SOC / 100.0,
    )


def plan_without_sun(battery, forecast: Optional[PlanningForecast], cfg=None) -> Optional[planner.Plan]:
    """The same plan as if the sun didn't shine: the counterfactual that shows
    how much buying the forecast sun actually saves."""
    if forecast is None:
        return None
    return plan_for(battery, replace(forecast, solar_kwh=[0.0] * len(forecast.solar_kwh)), cfg)


def decide(inp: brain.BrainInput, forecast: Optional[PlanningForecast],
           cfg=None) -> EnergyDecision:
    plan = plan_for(inp.battery, forecast, cfg)
    if plan is None:
        return brain.decide(inp)          # no forecast or solver failure: rules
    return brain.decide(replace(inp, planned_battery_kw=plan.battery_kw,
                                planned_grid_charge_kw=plan.grid_charge_now_kw,
                                plan_reason=plan.reason))
