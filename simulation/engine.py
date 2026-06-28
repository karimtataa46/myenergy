"""
Simulation engine — the physics.

Steps hour-by-hour through a day/month. Given a controller's battery command,
it enforces energy conservation, battery limits, and round-trip efficiency,
then computes grid flows, cost, and CO2.

The controller decides ONE number per hour: battery_ac_kwh
    > 0  => charge the battery (consumes energy at the AC bus)
    < 0  => discharge the battery (supplies energy to the AC bus)

The engine guarantees:   solar + grid_import + discharge = load + charge + export
"""

from dataclasses import dataclass, field
from typing import Callable, List

import factory as F


@dataclass
class StepState:
    """Everything a controller needs to make a decision for one hour."""
    hour: int
    solar_kwh: float
    load_kwh: float
    soc_kwh: float                  # current energy stored in battery
    capacity_kwh: float
    forecast_next_solar_kwh: float  # avg expected solar over next few hours
    forecast_tomorrow_deficit_kwh: float  # expected (load-solar) tomorrow
    # Full look-ahead window (current hour first), used by the optimal controller.
    # Simple rule controllers ignore these.
    forecast_solar_kwh: List[float] = field(default_factory=list)
    forecast_load_kwh: List[float] = field(default_factory=list)

    @property
    def soc_pct(self) -> float:
        return self.soc_kwh / self.capacity_kwh


@dataclass
class StepResult:
    hour: int
    solar_kwh: float
    load_kwh: float
    battery_ac_kwh: float       # +charge / -discharge at AC bus
    grid_import_kwh: float
    grid_export_kwh: float
    soc_kwh: float              # after this step
    cost_eur: float
    co2_kg: float


@dataclass
class Totals:
    cost_eur: float = 0.0
    grid_import_kwh: float = 0.0
    grid_export_kwh: float = 0.0
    solar_used_kwh: float = 0.0       # solar consumed on site (not exported)
    solar_total_kwh: float = 0.0
    load_kwh: float = 0.0
    co2_kg: float = 0.0
    steps: List[StepResult] = field(default_factory=list)

    @property
    def solar_fraction(self) -> float:
        return self.solar_used_kwh / self.load_kwh if self.load_kwh else 0.0


# Controller signature: takes StepState, returns desired battery_ac_kwh
Controller = Callable[[StepState], float]

# How many hours ahead the optimal controller plans over (rolling horizon).
HORIZON_HOURS = 36


def _apply_battery(soc_kwh: float, requested_ac_kwh: float) -> (float, float):
    """
    Apply a battery command with rate limits, SOC bounds, and efficiency.
    Returns (actual_battery_ac_kwh, new_soc_kwh).
    """
    cap = F.BATTERY_CAPACITY_KWH
    min_kwh = F.BATTERY_MIN_SOC * cap
    max_kwh = F.BATTERY_MAX_SOC * cap

    if requested_ac_kwh >= 0:
        # Charging: limited by rate and remaining room (accounting for efficiency)
        ac = min(requested_ac_kwh, F.BATTERY_MAX_CHARGE_KW)  # 1 hour slot
        stored = ac * F.CHARGE_EFFICIENCY
        room = max_kwh - soc_kwh
        if stored > room:
            stored = room
            ac = stored / F.CHARGE_EFFICIENCY
        return ac, soc_kwh + stored
    else:
        # Discharging: limited by rate and available energy above reserve
        ac = max(requested_ac_kwh, -F.BATTERY_MAX_DISCHARGE_KW)
        delivered = -ac                          # AC energy we want out
        drawn = delivered / F.DISCHARGE_EFFICIENCY
        available = soc_kwh - min_kwh
        if drawn > available:
            drawn = max(available, 0.0)
            delivered = drawn * F.DISCHARGE_EFFICIENCY
            ac = -delivered
        return ac, soc_kwh - drawn


def step(state: StepState, controller: Controller) -> StepResult:
    requested = controller(state)
    battery_ac, new_soc = _apply_battery(state.soc_kwh, requested)

    # Energy balance at the AC bus
    grid_net = state.load_kwh - state.solar_kwh + battery_ac
    grid_import = max(grid_net, 0.0)
    grid_export = max(-grid_net, 0.0)

    cost = grid_import * F.tariff(state.hour) - grid_export * F.FEED_IN_TARIFF
    co2 = grid_import * F.grid_co2(state.hour)

    return StepResult(
        hour=state.hour,
        solar_kwh=state.solar_kwh,
        load_kwh=state.load_kwh,
        battery_ac_kwh=round(battery_ac, 3),
        grid_import_kwh=round(grid_import, 3),
        grid_export_kwh=round(grid_export, 3),
        soc_kwh=round(new_soc, 3),
        cost_eur=round(cost, 4),
        co2_kg=round(co2, 4),
    )


def simulate(
    weather: List[F.DayWeather],
    controller: Controller,
    start_soc_kwh: float = 0.10 * F.BATTERY_CAPACITY_KWH,
) -> Totals:
    """Run the controller across a list of days. Returns accumulated Totals."""
    totals = Totals()
    soc = start_soc_kwh

    # Flatten the whole month into hour-by-hour arrays so any hour can look
    # ahead over the forecast horizon. (Perfect foresight — real forecasts
    # have error; that's measured separately.)
    all_solar = [day.solar_kwh(h) for day in weather for h in range(24)]
    all_load = [F.LOAD_PROFILE_KW[h] for _ in weather for h in range(24)]
    n = len(all_solar)

    for d, day in enumerate(weather):
        tomorrow = weather[d + 1] if d + 1 < len(weather) else day
        tomorrow_deficit = sum(
            max(F.LOAD_PROFILE_KW[h] - tomorrow.solar_kwh(h), 0) for h in range(24)
        )

        for h in range(24):
            t = d * 24 + h                       # absolute hour index
            solar = all_solar[t]
            load = all_load[t]

            # Forecast: average solar over next 3 hours (same day)
            next_hours = [day.solar_kwh(hh) for hh in range(h + 1, min(h + 4, 24))]
            fc_next = sum(next_hours) / len(next_hours) if next_hours else 0.0

            # Look-ahead window for the optimal controller (current hour first)
            end = min(t + HORIZON_HOURS, n)
            window_solar = all_solar[t:end]
            window_load = all_load[t:end]

            state = StepState(
                hour=h,
                solar_kwh=solar,
                load_kwh=load,
                soc_kwh=soc,
                capacity_kwh=F.BATTERY_CAPACITY_KWH,
                forecast_next_solar_kwh=fc_next,
                forecast_tomorrow_deficit_kwh=tomorrow_deficit,
                forecast_solar_kwh=window_solar,
                forecast_load_kwh=window_load,
            )

            res = step(state, controller)
            soc = res.soc_kwh

            totals.cost_eur += res.cost_eur
            totals.grid_import_kwh += res.grid_import_kwh
            totals.grid_export_kwh += res.grid_export_kwh
            totals.solar_total_kwh += solar
            totals.solar_used_kwh += min(solar, load) + max(
                min(solar - load, res.battery_ac_kwh) if res.battery_ac_kwh > 0 else 0, 0
            )
            totals.load_kwh += load
            totals.co2_kg += res.co2_kg
            totals.steps.append(res)

    totals.cost_eur = round(totals.cost_eur, 2)
    totals.co2_kg = round(totals.co2_kg, 1)
    return totals
