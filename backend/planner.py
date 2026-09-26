"""
Forecast-aware battery planner: the "wait for the sun" brain.

Every tick it takes the hourly forecast for the next 36 hours (solar, load and
price), plans the cheapest battery schedule over that whole window with the
linear program in simulation/optimizer.py, and returns only what to do THIS hour
plus a plain-language reason. Next tick it plans again with fresh numbers (a
receding horizon), so a wrong forecast is corrected as soon as reality differs.
"""
from dataclasses import dataclass, replace
from typing import Optional

from engine import HORIZON_HOURS
from models import BatteryState, PlanningForecast
from optimizer import optimal_battery_schedule


@dataclass
class Plan:
    battery_kw: float             # this hour: + charge / - discharge
    grid_charge_now_kw: float     # part of this hour's charging bought from the grid
    solar_to_battery_kwh: float   # free solar the plan expects to store in the next 24 h
    reason: str


def make_plan(battery: BatteryState, forecast: PlanningForecast, cfg,
              min_soc_frac: float, max_soc_frac: float) -> Optional[Plan]:
    """
    Plan the battery from the forecast. Returns None when there is nothing to
    plan with or the solver fails; the caller then falls back to the rule engine.
    """
    hours = min(len(forecast.solar_kwh), len(forecast.load_kwh), HORIZON_HOURS)
    if hours == 0:
        return None
    solar = list(forecast.solar_kwh[:hours])
    load = list(forecast.load_kwh[:hours])

    # Plan with THIS battery and the live system's own safety limits, so the plan
    # never asks for something the safety envelope in brain.py would refuse.
    plan_cfg = replace(
        cfg,
        battery_capacity_kwh=battery.capacity_kwh,
        battery_max_charge_kw=battery.max_charge_kw,
        battery_max_discharge_kw=battery.max_discharge_kw,
        battery_min_soc=max(cfg.battery_min_soc, min_soc_frac),
        battery_max_soc=min(cfg.battery_max_soc, max_soc_frac),
    )
    price = [cfg.tariff((forecast.hour + k) % 24) for k in range(hours)]
    feed_in = [cfg.feed_in_tariff] * hours
    soc_kwh = battery.soc_percent / 100.0 * battery.capacity_kwh

    schedule = optimal_battery_schedule(solar, load, price, feed_in, soc_kwh, cfg=plan_cfg)
    if schedule is None:
        return None

    charge, discharge = schedule["charge"], schedule["discharge"]
    surplus = [max(s - l, 0.0) for s, l in zip(solar, load)]
    from_solar = [min(c, s) for c, s in zip(charge, surplus)]

    battery_kw = float(charge[0] - discharge[0])
    grid_charge_now = float(charge[0] - from_solar[0])
    solar_to_battery = float(sum(from_solar[:24]))
    full = soc_kwh >= plan_cfg.battery_max_soc * battery.capacity_kwh - 1.0

    reason = _explain(battery_kw, grid_charge_now, solar_to_battery, price[0],
                      cfg.is_peak(forecast.hour), full)
    return Plan(battery_kw, grid_charge_now, solar_to_battery, reason)


def _explain(battery_kw, grid_charge_now, solar_to_battery, price, is_peak, full) -> str:
    """One sentence a facility manager can read on the dashboard."""
    if battery_kw > 0.5 and grid_charge_now > 0.5:
        return (f"Buying {grid_charge_now:.0f} kW at €{price:.2f}: the forecast sun will "
                f"only add ~{solar_to_battery:.0f} kWh, not enough for what's ahead")
    if battery_kw > 0.5:
        return f"Storing {battery_kw:.0f} kW of free solar surplus"
    if battery_kw < -0.5 and not is_peak and solar_to_battery > 5:
        return (f"Using the battery now: the forecast sun will refill it "
                f"with ~{solar_to_battery:.0f} kWh for free")
    if battery_kw < -0.5:
        return f"Discharging {-battery_kw:.0f} kW to avoid €{price:.2f} grid power"
    if full:
        return f"Battery full, the grid covers the load at €{price:.2f}"
    if not is_peak and solar_to_battery > 5:
        return (f"Waiting for the sun: the forecast will put ~{solar_to_battery:.0f} kWh "
                f"of free solar into the battery, so not buying grid now")
    return f"Holding the battery, the grid covers the load at €{price:.2f}"
