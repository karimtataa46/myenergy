"""
Two controllers, identical hardware. The whole product is the gap between them.

  reactive  = a normal "dumb" battery system: use solar, fill battery from
              surplus, drain it on deficit. No forecast, no price awareness.

  predictive (myEnergy) = forecast + tariff aware:
              - charges the battery from the cheap night grid, sized to what
                tomorrow actually needs (forecast-driven, no wasted cycles)
              - discharges during the expensive peak window to dodge €0.28/kWh
              - stores any solar surplus instead of dumping it cheap
"""

import factory as F
from engine import StepState


# ── Baseline: reactive self-consumption ──────────────────────────────────────

def reactive(s: StepState) -> float:
    """
    Dumb controller. Returns battery_ac_kwh (+charge / -discharge).
    Only ever moves the battery in response to a solar surplus/deficit RIGHT NOW.
    """
    net = s.solar_kwh - s.load_kwh
    if net > 0:
        # Surplus solar -> charge battery with it
        return net            # engine clamps to rate/room
    else:
        # Deficit -> discharge battery to cover it
        return net            # negative -> discharge, engine clamps to available


# ── myEnergy: predictive + tariff-aware ──────────────────────────────────────

# How full we want the battery by the start of the peak window, as a function
# of how much grid energy tomorrow's peak will actually need.
PEAK_HOURS = F.PEAK_END - F.PEAK_START


def predictive(s: StepState) -> float:
    """
    Smart controller. Returns battery_ac_kwh (+charge / -discharge).
    """
    cap = s.capacity_kwh
    net = s.solar_kwh - s.load_kwh
    peak_now = F.is_peak(s.hour)

    # 1) Solar surplus -> always store it (it's free; save it for the peak)
    if net > 0:
        return net

    deficit = -net

    if peak_now:
        # 2) Expensive hours: lean on the battery to avoid €0.28/kWh grid.
        #    Forecast refinement: if a strong solar surge is < a few hours away
        #    and the battery is getting low, keep a small reserve so we don't
        #    drain to nothing right before the sun covers us for free.
        solar_surge_incoming = s.forecast_next_solar_kwh > 0.5 * s.load_kwh
        reserve_floor = 0.30 if (solar_surge_incoming and s.soc_pct < 0.45) else 0.0
        usable = max(s.soc_kwh - (F.BATTERY_MIN_SOC + reserve_floor) * cap, 0.0)
        discharge = min(deficit, F.BATTERY_MAX_DISCHARGE_KW, usable)
        return -discharge

    else:
        # 3) Cheap night hours: grid covers the load directly. Meanwhile,
        #    pre-charge the battery for tomorrow's peak — but only as much as
        #    tomorrow will actually use. A sunny tomorrow => charge less and
        #    skip the round-trip loss. THIS is the forecast paying off.
        target_fraction = _precharge_target(s.forecast_tomorrow_deficit_kwh, cap)
        target_kwh = target_fraction * cap
        need = target_kwh - s.soc_kwh
        if need <= 0:
            return 0.0
        return min(need, F.BATTERY_MAX_CHARGE_KW)


def _precharge_target(tomorrow_deficit_kwh: float, cap: float) -> float:
    """
    Decide how full the battery should be by morning (fraction 0..1).
    Big expected deficit tomorrow -> fill it. Small deficit (sunny) -> partial.
    Capped at 100%; battery only helps for what the peak can actually absorb.
    """
    # We can usefully discharge ~ (1 - min_soc) * cap during the peak.
    usable_cap = (F.BATTERY_MAX_SOC - F.BATTERY_MIN_SOC) * cap
    if tomorrow_deficit_kwh >= usable_cap:
        return F.BATTERY_MAX_SOC          # full
    # Scale fill to expected need, but keep at least 40% so we always have some.
    frac = F.BATTERY_MIN_SOC + tomorrow_deficit_kwh / cap
    return max(0.40, min(F.BATTERY_MAX_SOC, frac))
