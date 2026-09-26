"""
Forecast-aware battery planner: the "wait for the sun" brain.

Every tick it takes the hourly forecast for the next 36 hours (solar, load and
price), plans the cheapest battery schedule over that whole window with the
linear program in simulation/optimizer.py, and returns only what to do THIS hour
plus a plain-language reason. Next tick it plans again with fresh numbers (a
receding horizon), so a wrong forecast is corrected as soon as reality differs.
"""
from dataclasses import dataclass, field, replace
from typing import Callable, List, Optional

from engine import HORIZON_HOURS
from models import BatteryState, PlanningForecast
from optimizer import optimal_battery_schedule


@dataclass
class PlanHour:
    offset: int            # hours from now (0 = the current hour)
    solar_kw: float
    load_kw: float
    grid_buy_kw: float     # bought from the grid INTO the battery this hour
    battery_pct: float     # planned battery level at the END of this hour
    price: float
    cheap: bool


@dataclass
class Plan:
    battery_kw: float             # this hour: + charge / - discharge
    grid_charge_now_kw: float     # part of this hour's charging bought from the grid
    solar_to_battery_kwh: float   # free solar the plan expects to store in the next 24 h
    reason: str
    hours: List[PlanHour] = field(default_factory=list)   # the whole planned timeline


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
    timeline = [
        PlanHour(offset=k, solar_kw=solar[k], load_kw=load[k],
                 grid_buy_kw=float(charge[k] - from_solar[k]),
                 battery_pct=float(schedule["soc"][k] / battery.capacity_kwh * 100),
                 price=price[k], cheap=not cfg.is_peak((forecast.hour + k) % 24))
        for k in range(hours)
    ]
    return Plan(battery_kw, grid_charge_now, solar_to_battery, reason, timeline)


@dataclass
class PlanSummary:
    buy_tonight_kwh: float          # grid energy bought for the battery in the next cheap window
    buy_without_sun_kwh: float      # what it would buy tonight if the sun didn't shine
    buy_first: Optional[int]        # offset of the first hour it buys (None = buys nothing)
    buy_last: Optional[int]         # offset of the last hour it buys
    buy_price: Optional[float]
    solar_to_battery_kwh: float     # free solar stored in the next 24 h
    fullest_pct: float              # highest planned battery level in the next 24 h ...
    fullest_offset: int             # ... reached at the end of this hour
    tone: str                       # "sun" | "buy" | "hold"
    headline: str
    detail: str


def _tonight(plan: Plan):
    """The next cheap window (the current one if we're in it) and what is bought in it."""
    start = next((h.offset for h in plan.hours if h.cheap), None)
    window = []
    if start is not None:
        for h in plan.hours[start:]:
            if not h.cheap:
                break
            window.append(h)
    buying = [h for h in window if h.grid_buy_kw > 0.5]
    return buying, sum(h.grid_buy_kw for h in window)


# The sun must save at least this much buying before the story credits it.
SUN_CREDIT_KWH = 5.0


def summarize(plan: Plan, fmt_time: Callable[[int], str],
              plan_without_sun: Optional[Plan] = None) -> PlanSummary:
    """
    Turn the hour-by-hour plan into what a facility manager actually asks: how
    much am I buying tonight, what does the sun do, how full will the battery
    get, and why. fmt_time(offset) renders the START of an hour, so the caller
    decides the timezone.

    plan_without_sun is the same plan as if the sun didn't shine. Comparing the
    two is the honest way to say whether the forecast sun changed tonight's
    purchase; comparing "bought" with "stored" would mix unrelated numbers.
    """
    buying, buy = _tonight(plan)
    buy_without_sun = _tonight(plan_without_sun)[1] if plan_without_sun else buy
    sun_saves = buy_without_sun - buy
    first = buying[0].offset if buying else None
    last = buying[-1].offset if buying else None
    price = buying[0].price if buying else None
    solar = plan.solar_to_battery_kwh
    fullest = max(plan.hours[:24], key=lambda h: h.battery_pct)
    when = f"between {fmt_time(first)} and {fmt_time(last + 1)}" if buying else ""

    if sun_saves > SUN_CREDIT_KWH:
        tone, headline = "sun", "Waiting for the sun"
        bought = f"only {buy:.0f} kWh is bought tonight, {when}," if buying else "nothing is bought tonight,"
        detail = (f"The forecast sun will do part of the work, so {bought} "
                  f"instead of {buy_without_sun:.0f} kWh.")
    elif buying:
        tone, headline = "buy", "Buying cheap power tonight"
        if solar > SUN_CREDIT_KWH:
            detail = (f"{buy:.0f} kWh is bought {when} at €{price:.2f} to cover the hours "
                      f"before the sun is strong enough. The sun then adds about {solar:.0f} kWh.")
        else:
            detail = (f"Tomorrow looks too dark for the sun to charge the battery, "
                      f"so {buy:.0f} kWh is bought {when} at €{price:.2f}.")
    elif solar > SUN_CREDIT_KWH:
        tone, headline = "sun", "Running on the sun"
        detail = (f"Nothing needs to be bought tonight. The sun will put about "
                  f"{solar:.0f} kWh into the battery for free.")
    else:
        tone, headline = "hold", "Holding steady"
        detail = ("No battery purchase is planned in the next 24 hours. "
                  "The grid covers the load whenever the battery can't.")

    return PlanSummary(buy, buy_without_sun, first, last, price, solar, fullest.battery_pct,
                       fullest.offset, tone, headline, detail)


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
