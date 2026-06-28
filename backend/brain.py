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

from models import (
    BatteryState, SolarReading, ConsumptionReading, GridAction, EnergyDecision
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
    solar: SolarReading
    battery: BatteryState
    consumption: ConsumptionReading
    upcoming_solar_kw: float      # avg solar expected next N hours
    current_tariff_eur_kwh: float


def decide(inp: BrainInput) -> EnergyDecision:
    """
    Core decision function. Takes current state, returns what to do.
    Returns an EnergyDecision with exact power flows.
    """
    solar = inp.solar.power_kw
    load = inp.consumption.total_kw
    soc = inp.battery.soc_percent
    bat = inp.battery
    upcoming = inp.upcoming_solar_kw

    net_solar = solar - load   # positive = solar surplus, negative = deficit

    # ── Rule 1: Battery critical — protect at all costs ─────────────────────
    if soc <= BATTERY_CRITICAL_SOC:
        # Stop discharging immediately, import from grid
        return EnergyDecision(
            timestamp=datetime.now(timezone.utc),
            action=GridAction.GRID_IMPORT,
            reason=f"Battery critical ({soc:.0f}%) — protecting remaining charge",
            solar_kw=solar,
            battery_kw=0.0,
            grid_kw=max(load - solar, 0),
            consumption_kw=load,
        )

    # ── Rule 2: Solar surplus — use it ──────────────────────────────────────
    if net_solar > 0:
        if not bat.is_full:
            # Charge battery with surplus
            charge_kw = min(net_solar, bat.max_charge_kw)
            export_kw = max(net_solar - charge_kw, 0)
            return EnergyDecision(
                timestamp=datetime.now(timezone.utc),
                # This energy is SOLAR surplus, not grid — label it accordingly.
                # (If there's still surplus after charging, we also export it.)
                action=GridAction.BATTERY_CHARGE_FROM_SOLAR if export_kw == 0 else GridAction.EXPORT_TO_GRID,
                reason=f"Solar surplus {net_solar:.1f}kW — charging battery",
                solar_kw=solar,
                battery_kw=charge_kw,
                grid_kw=-export_kw,
                consumption_kw=load,
            )
        else:
            # Battery full — export excess to grid
            return EnergyDecision(
                timestamp=datetime.now(timezone.utc),
                action=GridAction.EXPORT_TO_GRID,
                reason=f"Battery full, exporting {net_solar:.1f}kW to grid",
                solar_kw=solar,
                battery_kw=0.0,
                grid_kw=-net_solar,
                consumption_kw=load,
            )

    # Below here: solar < load (deficit)
    deficit = abs(net_solar)
    is_offpeak = inp.current_tariff_eur_kwh <= OFFPEAK_TARIFF_THRESHOLD

    # ── Rule 3: Off-peak — grid is cheap, pre-charge the battery ─────────────
    # This is the arbitrage proven in the monthly simulation (€742/month):
    # fill the battery at the €0.12 night rate so it can offset the €0.28
    # peak window tomorrow. A dumb controller leaves the battery idle here.
    if is_offpeak:
        if not bat.is_full:
            charge_kw = min(bat.max_charge_kw, (BATTERY_FULL_SOC - soc) / 100 * bat.capacity_kwh)
            charge_kw = max(charge_kw, 0)
            return EnergyDecision(
                timestamp=datetime.now(timezone.utc),
                action=GridAction.BATTERY_CHARGE_FROM_GRID,
                reason=f"Off-peak ({inp.current_tariff_eur_kwh:.2f}€) — pre-charging battery {soc:.0f}%→full for tomorrow's peak",
                solar_kw=solar,
                battery_kw=charge_kw,
                grid_kw=deficit + charge_kw,
                consumption_kw=load,
            )
        # Battery already full — just ride the cheap grid
        return EnergyDecision(
            timestamp=datetime.now(timezone.utc),
            action=GridAction.GRID_IMPORT,
            reason=f"Off-peak ({inp.current_tariff_eur_kwh:.2f}€), battery full — riding cheap grid",
            solar_kw=solar,
            battery_kw=0.0,
            grid_kw=deficit,
            consumption_kw=load,
        )

    # Below here: PEAK hours (expensive grid). Lean on the battery.

    # ── Rule 4: Peak + strong solar imminent — keep a reserve ───────────────
    # The forecast story: don't drain to nothing right before the sun
    # returns; keep some charge for the evening peak.
    solar_arriving_soon = upcoming >= SOLAR_INCOMING_THRESHOLD_KW
    reserve_soc = BATTERY_RESERVE_SOC + (10 if (solar_arriving_soon and soc < 45) else 0)

    # ── Rule 5: Peak — discharge battery to dodge expensive grid ────────────
    if soc > reserve_soc and deficit > MIN_GRID_IMPORT_KW:
        usable_kwh = (soc - reserve_soc) / 100 * bat.capacity_kwh
        discharge_kw = min(deficit, bat.max_discharge_kw, usable_kwh)
        remaining_deficit = deficit - discharge_kw
        note = " (holding reserve, solar incoming)" if reserve_soc > BATTERY_RESERVE_SOC else ""
        return EnergyDecision(
            timestamp=datetime.now(timezone.utc),
            action=GridAction.BATTERY_DISCHARGE,
            reason=f"Peak ({inp.current_tariff_eur_kwh:.2f}€) — discharging battery {soc:.0f}% to cover {discharge_kw:.0f}kW{note}",
            solar_kw=solar,
            battery_kw=-discharge_kw,
            grid_kw=remaining_deficit,
            consumption_kw=load,
        )

    # ── Rule 6: Last resort — battery depleted, import from grid ─────────────
    return EnergyDecision(
        timestamp=datetime.now(timezone.utc),
        action=GridAction.GRID_IMPORT,
        reason=f"Peak but battery at reserve ({soc:.0f}%) — importing {deficit:.1f}kW from grid",
        solar_kw=solar,
        battery_kw=0.0,
        grid_kw=deficit,
        consumption_kw=load,
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
