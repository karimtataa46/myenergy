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
    # The facility's parameters. Defaults to the standard factory so existing
    # callers that don't pass one behave exactly as before.
    cfg: "F.FacilityConfig" = field(default_factory=lambda: F.DEFAULT_CONFIG)

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
        # Self-consumed solar / load. Solar can serve load directly AND via the
        # battery, but it can never serve MORE than the load it covers, so the
        # fraction is bounded to [0,1]. (Counting AC-in battery charge slightly
        # over-states self-use when solar hugely exceeds load; cap it here.)
        if not self.load_kwh:
            return 0.0
        return min(1.0, self.solar_used_kwh / self.load_kwh)


# Controller signature: takes StepState, returns desired battery_ac_kwh
Controller = Callable[[StepState], float]

# How many hours ahead the optimal controller plans over (rolling horizon).
HORIZON_HOURS = 36


def _apply_battery(soc_kwh: float, requested_ac_kwh: float, cfg=None) -> (float, float):
    """
    Apply a battery command with rate limits, SOC bounds, and efficiency.
    Returns (actual_battery_ac_kwh, new_soc_kwh).
    """
    if cfg is None:
        cfg = F.DEFAULT_CONFIG
    cap = cfg.battery_capacity_kwh
    min_kwh = cfg.battery_min_soc * cap
    max_kwh = cfg.battery_max_soc * cap

    if requested_ac_kwh >= 0:
        # Charging: limited by rate and remaining room (accounting for efficiency)
        ac = min(requested_ac_kwh, cfg.battery_max_charge_kw)  # 1 hour slot
        stored = ac * cfg.charge_efficiency
        room = max_kwh - soc_kwh
        if stored > room:
            stored = room
            ac = stored / cfg.charge_efficiency
        return ac, soc_kwh + stored
    else:
        # Discharging: limited by rate and available energy above reserve
        ac = max(requested_ac_kwh, -cfg.battery_max_discharge_kw)
        delivered = -ac                          # AC energy we want out
        drawn = delivered / cfg.discharge_efficiency
        available = soc_kwh - min_kwh
        if drawn > available:
            drawn = max(available, 0.0)
            delivered = drawn * cfg.discharge_efficiency
            ac = -delivered
        return ac, soc_kwh - drawn


def step(state: StepState, controller: Controller) -> StepResult:
    cfg = state.cfg
    requested = controller(state)
    battery_ac, new_soc = _apply_battery(state.soc_kwh, requested, cfg)

    # Energy balance at the AC bus
    grid_net = state.load_kwh - state.solar_kwh + battery_ac
    grid_import = max(grid_net, 0.0)
    grid_export = max(-grid_net, 0.0)

    cost = grid_import * cfg.tariff(state.hour) - grid_export * cfg.feed_in_tariff
    co2 = grid_import * cfg.grid_co2(state.hour)

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
    start_soc_kwh: float = None,
    cfg=None,
) -> Totals:
    """Run the controller across a list of days. Returns accumulated Totals."""
    if cfg is None:
        cfg = F.DEFAULT_CONFIG
    if start_soc_kwh is None:
        start_soc_kwh = cfg.battery_min_soc * cfg.battery_capacity_kwh
    totals = Totals()
    soc = start_soc_kwh

    # Flatten the whole month into hour-by-hour arrays so any hour can look
    # ahead over the forecast horizon. Solar and load are built from THIS
    # facility's config (so a bigger array / different load scales correctly).
    all_solar = [cfg.solar_kwh(h, day.cloud_factor) for day in weather for h in range(24)]
    all_load = [cfg.load_profile_kw[h] for _ in weather for h in range(24)]
    n = len(all_solar)

    for d, day in enumerate(weather):
        tomorrow = weather[d + 1] if d + 1 < len(weather) else day
        tomorrow_deficit = sum(
            max(cfg.load_profile_kw[h] - cfg.solar_kwh(h, tomorrow.cloud_factor), 0)
            for h in range(24)
        )

        for h in range(24):
            t = d * 24 + h                       # absolute hour index
            solar = all_solar[t]
            load = all_load[t]

            # Forecast: average solar over next 3 hours (same day)
            next_hours = [cfg.solar_kwh(hh, day.cloud_factor)
                          for hh in range(h + 1, min(h + 4, 24))]
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
                capacity_kwh=cfg.battery_capacity_kwh,
                forecast_next_solar_kwh=fc_next,
                forecast_tomorrow_deficit_kwh=tomorrow_deficit,
                forecast_solar_kwh=window_solar,
                forecast_load_kwh=window_load,
                cfg=cfg,
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
