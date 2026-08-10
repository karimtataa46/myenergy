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
OFFPEAK_TARIFF_THRESHOLD = 0.15  # €/kWh — at or below this = cheap night rate


@dataclass
class BrainInput:
    """MODIFIED: Replaced monolithic consumption with base load and shiftable devices."""
    solar: SolarReading
    battery: BatteryState
    base_load_kw: float                      # NEW: Power used by non-controllable things (lights, servers)
    shiftable_devices: List[ShiftableDevice] # NEW: List of devices the brain is allowed to control
    upcoming_solar_kw: float
    current_tariff_eur_kwh: float


def decide(inp: BrainInput) -> EnergyDecision:
    now = datetime.now(timezone.utc)
    solar = inp.solar.power_kw
    soc = inp.battery.soc_percent
    bat = inp.battery
    upcoming = inp.upcoming_solar_kw
    is_offpeak = inp.current_tariff_eur_kwh <= OFFPEAK_TARIFF_THRESHOLD

    # =========================================================================
    # STAGE 1: DEVICE SCHEDULING (Load Shifting)
    # =========================================================================
    device_commands = {}
    active_shiftable_kw = 0.0

    # Calculate how much free solar we have before turning on flexible devices
    available_solar_kw = max(0.0, solar - inp.base_load_kw)

    # Filter out devices that are already done, and sort the rest by urgency
    unfulfilled = [d for d in inp.shiftable_devices if not d.is_fulfilled]
    unfulfilled.sort(key=lambda d: d.urgency(now), reverse=True)

    for dev in unfulfilled:
        turn_on = False

        # Rule A: Non-interruptible device is already running — don't stop it
        if not dev.is_interruptible and dev.is_on:
            turn_on = True
        # Rule B: Deadline is imminent — MUST turn on right now
        elif dev.urgency(now) >= 1.0:
            turn_on = True
        # Rule C: Grid is very cheap — turn on now to avoid peak prices later
        elif is_offpeak:
            turn_on = True
        # Rule D: We have enough free solar surplus to power this device
        elif available_solar_kw >= dev.power_draw_kw:
            turn_on = True
            available_solar_kw -= dev.power_draw_kw  # Deduct from our free solar pool

        device_commands[dev.id] = turn_on
        if turn_on:
            active_shiftable_kw += dev.power_draw_kw

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

    # Rule 3: Off-peak — grid is cheap, pre-charge the battery
    if is_offpeak:
        if not bat.is_full:
            # Note: We calculate power limit based on capacity, but only bound it by max_charge_kw
            charge_kw = bat.max_charge_kw
            return EnergyDecision(
                timestamp=now,
                action=GridAction.BATTERY_CHARGE_FROM_GRID,
                reason=f"Off-peak ({inp.current_tariff_eur_kwh:.2f}€) — pre-charging battery for tomorrow",
                solar_kw=solar,
                battery_kw=charge_kw,
                grid_kw=deficit + charge_kw,
                consumption_kw=total_load,
                device_commands=device_commands
            )
        return EnergyDecision(
            timestamp=now,
            action=GridAction.GRID_IMPORT,
            reason=f"Off-peak ({inp.current_tariff_eur_kwh:.2f}€), battery full — riding cheap grid",
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


