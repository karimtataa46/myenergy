"""
myEnergy Decision Engine

This is the core intelligence. It reads current state + weather forecast
and decides what to do with the battery every tick.

Design: deterministic rule-based with priority ordering.
This is the RIGHT approach before adding ML — you need a baseline
that works reliably before you can measure if ML improves it.

Decision priority (highest first):
  1. Critical battery → emergency protect (never go below 10%)
  2. Solar > consumption → charge battery or export
  3. Solar incoming soon → hold battery, wait for solar
  4. Battery has charge → discharge to avoid grid
  5. Last resort → import from grid
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List, Dict
from models import (
    BatteryState, SolarReading, ConsumptionReading,
    ShiftableDevice, GridAction, EnergyDecision,
)


# Thresholds — these are the tunable parameters of the engine
BATTERY_CRITICAL_SOC = 15.0      # % — protect below this
BATTERY_RESERVE_SOC = 20.0       # % — keep in reserve for emergencies
BATTERY_FULL_SOC = 95.0          # % — stop charging above this
SOLAR_INCOMING_THRESHOLD_KW = 15.0  # kW — "meaningful" solar coming
SOLAR_WAIT_HORIZON_HOURS = 2     # hours — look ahead window
MIN_GRID_IMPORT_KW = 2.0         # kW — don't bother avoiding tiny grid draws
OFFPEAK_TARIFF_THRESHOLD = 0.15  # €/kWh — fallback "cheap" rate if no price is passed

# Battery economics — a battery is not a free store. Charging then discharging
# loses energy to round-trip inefficiency, and every kWh cycled ages the cells.
# Arbitrage only pays when the price spread beats BOTH of these.
BATTERY_ROUNDTRIP_EFFICIENCY = 0.88   # AC→battery→AC; ~88% is typical Li-ion + inverter
BATTERY_WEAR_COST_EUR_KWH = 0.04      # amortised degradation per kWh of throughput


def _arbitrage_worthwhile(peak_price: float, offpeak_price: float) -> bool:
    """
    Is it worth buying a kWh at the off-peak price, storing it, and discharging
    it at peak? Only if the peak price — AFTER round-trip losses — still beats the
    off-peak price PLUS the wear cost of cycling the battery:

        η · peak  >  offpeak + wear

    This is the honesty gate: without it the brain "saves" money that the losses
    and degradation quietly eat, and on a narrow tariff spread it loses money.
    """
    return peak_price * BATTERY_ROUNDTRIP_EFFICIENCY > offpeak_price + BATTERY_WEAR_COST_EUR_KWH


@dataclass
class BrainInput:
    """MODIFIED: Replaced monolithic consumption with base load and shiftable devices."""
    solar: SolarReading
    battery: BatteryState
    base_load_kw: float                      # NEW: Power used by non-controllable things (lights, servers)
    shiftable_devices: List[ShiftableDevice] # NEW: List of devices the brain is allowed to control
    upcoming_solar_kw: float
    current_tariff_eur_kwh: float
    # Facility tariff endpoints — let the brain reason about the real spread and
    # define "off-peak" relative to this site instead of a hard-coded constant.
    peak_price_eur_kwh: float = 0.0
    offpeak_price_eur_kwh: float = 0.0
    # Peak-demand ceiling (kW). Base load + flexible devices + battery charging must
    # stay under this so we never set a costly new monthly demand peak. inf = no cap.
    demand_target_kw: float = float('inf')


def decide(inp: BrainInput) -> EnergyDecision:
    now = datetime.now(timezone.utc)
    solar = inp.solar.power_kw
    soc = inp.battery.soc_percent
    bat = inp.battery
    upcoming = inp.upcoming_solar_kw
    # "Off-peak" = at (or below) this site's own cheap rate. Prefer the real price
    # so it works for any country's tariff; fall back to the fixed threshold.
    if inp.offpeak_price_eur_kwh > 0:
        is_offpeak = inp.current_tariff_eur_kwh <= inp.offpeak_price_eur_kwh + 1e-9
    else:
        is_offpeak = inp.current_tariff_eur_kwh <= OFFPEAK_TARIFF_THRESHOLD

    # Only cycle the battery for grid arbitrage if the spread beats losses + wear.
    # No prices passed → keep legacy behaviour (assume worthwhile).
    if inp.peak_price_eur_kwh > 0 and inp.offpeak_price_eur_kwh > 0:
        arbitrage_ok = _arbitrage_worthwhile(inp.peak_price_eur_kwh, inp.offpeak_price_eur_kwh)
    else:
        arbitrage_ok = True

    # =========================================================================
    # STAGE 1: DEVICE SCHEDULING (load shifting) — with equipment min-runtime
    # locks and a demand-charge cap on how much grid load we stack at once.
    # =========================================================================
    device_commands = {}
    active_shiftable_kw = 0.0

    # Track grid draw as we commit loads. The base load claims grid first (after
    # any free solar); each optional device we switch on adds to it and must stay
    # under the demand ceiling.
    solar_surplus = max(0.0, solar - inp.base_load_kw)   # free solar after base load
    grid_used = max(0.0, inp.base_load_kw - solar)       # grid the base load already pulls

    # Filter out devices that are already done, and sort the rest by urgency
    unfulfilled = [d for d in inp.shiftable_devices if not d.is_fulfilled]
    unfulfilled.sort(key=lambda d: d.urgency(now), reverse=True)

    for dev in unfulfilled:
        # A device is "forced" on when its deadline demands it, when it's a
        # non-interruptible cycle already running, or when it was switched on too
        # recently to stop (min-runtime lock). Forced devices override the cap.
        must_run = (not dev.is_interruptible and dev.is_on) or dev.urgency(now) >= 1.0
        locked_on = dev.locked_on(now)
        forced = must_run or locked_on

        if locked_on:
            turn_on = True                          # can't switch off yet
        elif dev.locked_off(now) and not must_run:
            turn_on = False                         # can't restart yet (anti short-cycle)
        elif must_run:
            turn_on = True                          # deadline / mid-cycle
        elif solar_surplus >= dev.power_draw_kw:
            turn_on = True                          # free solar surplus covers it
        elif is_offpeak:
            turn_on = True                          # cheap grid window
        else:
            turn_on = False                         # peak & no surplus → wait

        if turn_on:
            from_solar = min(solar_surplus, dev.power_draw_kw)
            from_grid = dev.power_draw_kw - from_solar
            # Demand cap: an OPTIONAL grid-powered device must fit under the peak
            # ceiling. A forced device overrides it (a missed deadline or a damaged
            # motor costs more than the demand charge).
            if from_grid > 0 and not forced and grid_used + from_grid > inp.demand_target_kw:
                turn_on = False                     # defer to protect the monthly peak
            else:
                solar_surplus -= from_solar
                grid_used += from_grid
                active_shiftable_kw += dev.power_draw_kw

        device_commands[dev.id] = turn_on

    # The actual load we must satisfy this tick
    total_load = inp.base_load_kw + active_shiftable_kw
    net_solar = solar - total_load  # Positive = surplus, Negative = deficit

    # =========================================================================
    # STAGE 2: BATTERY & GRID DISPATCH
    # =========================================================================

    # Rule 1: Battery critical — protect at all costs
    if soc <= BATTERY_CRITICAL_SOC:
        return EnergyDecision(
            timestamp=now,
            action=GridAction.GRID_IMPORT,
            reason=f"Battery critical ({soc:.0f}%) — protecting remaining charge",
            solar_kw=solar,
            battery_kw=0.0,
            grid_kw=max(total_load - solar, 0.0),
            consumption_kw=total_load,
            device_commands=device_commands
        )

    # Rule 2: Solar surplus — charge battery or export
    if net_solar > 0:
        if not bat.is_full:
            charge_kw = min(net_solar, bat.max_charge_kw)
            export_kw = max(net_solar - charge_kw, 0.0)
            return EnergyDecision(
                timestamp=now,
                action=GridAction.BATTERY_CHARGE_FROM_SOLAR if export_kw == 0 else GridAction.EXPORT_TO_GRID,
                reason=f"Solar surplus {net_solar:.1f}kW — charging battery",
                solar_kw=solar,
                battery_kw=charge_kw,
                grid_kw=-export_kw,
                consumption_kw=total_load,
                device_commands=device_commands
            )
        else:
            return EnergyDecision(
                timestamp=now,
                action=GridAction.EXPORT_TO_GRID,
                reason=f"Battery full, exporting {net_solar:.1f}kW to grid",
                solar_kw=solar,
                battery_kw=0.0,
                grid_kw=-net_solar,
                consumption_kw=total_load,
                device_commands=device_commands
            )

    # Below here: solar < load (deficit)
    deficit = abs(net_solar)

    # Rule 3: Off-peak — pre-charge the battery, but only when it actually pays
    # (spread beats round-trip losses + wear) AND the extra charging fits under
    # the demand-charge ceiling.
    if is_offpeak:
        charge_headroom = max(0.0, inp.demand_target_kw - deficit)   # room under the cap
        charge_kw = min(bat.max_charge_kw, charge_headroom)
        if (not bat.is_full) and arbitrage_ok and charge_kw > 0.5:
            return EnergyDecision(
                timestamp=now,
                action=GridAction.BATTERY_CHARGE_FROM_GRID,
                reason=f"Off-peak ({inp.current_tariff_eur_kwh:.2f}€) — pre-charging {charge_kw:.0f}kW (net-positive after losses)",
                solar_kw=solar,
                battery_kw=charge_kw,
                grid_kw=deficit + charge_kw,
                consumption_kw=total_load,
                device_commands=device_commands
            )
        # Not pre-charging — say why, honestly.
        if bat.is_full:
            why = "battery full"
        elif not arbitrage_ok:
            why = "spread below losses+wear"
        else:
            why = "demand cap reached"
        return EnergyDecision(
            timestamp=now,
            action=GridAction.GRID_IMPORT,
            reason=f"Off-peak ({inp.current_tariff_eur_kwh:.2f}€), {why} — riding cheap grid at {deficit:.1f}kW",
            solar_kw=solar,
            battery_kw=0.0,
            grid_kw=deficit,
            consumption_kw=total_load,
            device_commands=device_commands
        )

    # Rule 4: Peak + strong solar imminent — keep a reserve
    solar_arriving_soon = upcoming >= SOLAR_INCOMING_THRESHOLD_KW
    reserve_soc = BATTERY_RESERVE_SOC + (10 if (solar_arriving_soon and soc < 45) else 0)

    # Rule 5: Peak — discharge battery to dodge expensive grid
    if soc > reserve_soc and deficit > MIN_GRID_IMPORT_KW:
        # BUG FIX: Removed usable_kwh constraint. Power should only be constrained by inverter limits.
        discharge_kw = min(deficit, bat.max_discharge_kw)
        remaining_deficit = deficit - discharge_kw
        note = " (holding reserve, solar incoming)" if reserve_soc > BATTERY_RESERVE_SOC else ""
        return EnergyDecision(
            timestamp=now,
            action=GridAction.BATTERY_DISCHARGE,
            reason=f"Peak ({inp.current_tariff_eur_kwh:.2f}€) — discharging {discharge_kw:.0f}kW{note}",
            solar_kw=solar,
            battery_kw=-discharge_kw,
            grid_kw=remaining_deficit,
            consumption_kw=total_load,
            device_commands=device_commands
        )

    # Rule 6: Last resort — battery depleted to reserve, import from grid
    return EnergyDecision(
        timestamp=now,
        action=GridAction.GRID_IMPORT,
        reason=f"Peak but battery at reserve ({soc:.0f}%) — importing {deficit:.1f}kW from grid",
        solar_kw=solar,
        battery_kw=0.0,
        grid_kw=deficit,
        consumption_kw=total_load,
        device_commands=device_commands
    )

def solar_only_mode(solar: float, load: float, bat: BatteryState) -> EnergyDecision:
    """When solar exactly meets load (rare, but handle it)."""
    return EnergyDecision(
        timestamp=datetime.now(timezone.utc),
        action=GridAction.SOLAR_ONLY,
        reason="Solar exactly meeting load — zero grid draw",
        solar_kw=solar,
        battery_kw=0.0,
        grid_kw=0.0,
        consumption_kw=load,
    )


