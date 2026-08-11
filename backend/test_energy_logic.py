"""
Tests for the three energy-engineering upgrades to the decision brain:

  1. Demand-charge cap   — flexible loads + battery charging never stack past the
                           demand ceiling (unless a device is FORCED on).
  2. Arbitrage gate      — the battery only pre-charges from grid when the price
                           spread beats round-trip losses + wear.
  3. Min-runtime locks   — devices don't short-cycle faster than their limits.

Standalone runner (no pytest): `python3 test_energy_logic.py`.
"""

from datetime import datetime, timezone, timedelta

import models
import brain
from models import GridAction

NOW = datetime.now(timezone.utc)

_passed = 0
_failed = 0


def check(name, cond, detail=""):
    global _passed, _failed
    if cond:
        _passed += 1
        print(f"  [PASS] {name}")
    else:
        _failed += 1
        print(f"  [FAIL] {name}   {detail}")


# ── builders ─────────────────────────────────────────────────────────────────
def mk_battery(soc=60.0, cap=200.0, chg=50.0, dis=50.0):
    return models.BatteryState(timestamp=NOW, soc_percent=soc, power_kw=0.0,
                               capacity_kwh=cap, max_charge_kw=chg, max_discharge_kw=dis)


def mk_solar(kw=0.0):
    return models.SolarReading(timestamp=NOW, power_kw=kw, irradiance_wm2=0.0)


def mk_dev(id, kw, is_on=False, hours_deadline=12.0, kwh=40.0, interruptible=True,
           min_on=0.0, min_off=0.0, last_change=None):
    return models.ShiftableDevice(
        id=id, name=id, power_draw_kw=kw, is_on=is_on,
        must_finish_by=NOW + timedelta(hours=hours_deadline),
        remaining_kwh_needed=kwh, is_interruptible=interruptible,
        min_on_minutes=min_on, min_off_minutes=min_off, last_change_at=last_change)


def mk_input(base, devices, tariff, solar=0.0, soc=60.0,
             peak=0.28, offpeak=0.12, demand=95.0, upcoming=0.0):
    return brain.BrainInput(
        solar=mk_solar(solar), battery=mk_battery(soc),
        base_load_kw=base, shiftable_devices=devices, upcoming_solar_kw=upcoming,
        current_tariff_eur_kwh=tariff, peak_price_eur_kwh=peak,
        offpeak_price_eur_kwh=offpeak, demand_target_kw=demand)


EPS = 1e-6

# ── 1. DEMAND-CHARGE CAP ─────────────────────────────────────────────────────
print("\n1) DEMAND-CHARGE CAP")

# Night: base 27 + EV 11 + heater 15 = 53; both fit under 95, and battery charge
# is capped to the 42 kW of headroom so total grid import lands exactly on 95.
devs = [mk_dev("ev", 11, kwh=40, hours_deadline=12),
        mk_dev("wh", 15, kwh=10, hours_deadline=4, interruptible=False)]
d = brain.decide(mk_input(base=27, devices=devs, tariff=0.12, demand=95))
check("Both devices run when they fit under the cap",
      d.device_commands["ev"] and d.device_commands["wh"], d.device_commands)
check("Grid import never exceeds the demand ceiling",
      d.grid_kw <= 95 + EPS, f"grid_kw={d.grid_kw}")
check("Battery charge is throttled to the headroom (< max 50 kW)",
      d.action == GridAction.BATTERY_CHARGE_FROM_GRID and 0 < d.battery_kw <= 42 + EPS,
      f"action={d.action.value} battery_kw={d.battery_kw}")

# Tight cap: EV fits (27+11=38), heater would breach (53>40) and is optional -> deferred.
d = brain.decide(mk_input(base=27, devices=[mk_dev("ev", 11), mk_dev("wh", 15, hours_deadline=4)],
                          tariff=0.12, demand=40))
check("Optional device deferred when it would breach the cap",
      d.device_commands["ev"] and not d.device_commands["wh"], d.device_commands)
check("Grid stays under the tight cap after deferral",
      d.grid_kw <= 40 + EPS, f"grid_kw={d.grid_kw}")

# A FORCED (deadline-imminent) device overrides the cap.
urgent = mk_dev("urgent", 20, kwh=10, hours_deadline=0.1)   # urgency = 0.5h / 0.1h = 5
d = brain.decide(mk_input(base=90, devices=[urgent], tariff=0.28, demand=95))
check("Must-run device overrides the demand cap (deadline > demand charge)",
      d.device_commands["urgent"], d.device_commands)

# ── 2. ARBITRAGE GATE (efficiency + wear) ────────────────────────────────────
print("\n2) ARBITRAGE GATE")

check("Helper: wide spread is worthwhile (0.45 vs 0.25)",
      brain._arbitrage_worthwhile(0.45, 0.25) is True)
check("Helper: narrow spread is NOT worthwhile (0.28 vs 0.26)",
      brain._arbitrage_worthwhile(0.28, 0.26) is False)
check("Helper: demo spread is worthwhile (0.28 vs 0.12)",
      brain._arbitrage_worthwhile(0.28, 0.12) is True)

# Profitable spread -> pre-charges from grid at off-peak.
d = brain.decide(mk_input(base=27, devices=[], tariff=0.12, peak=0.28, offpeak=0.12))
check("Pre-charges from grid when the spread pays",
      d.action == GridAction.BATTERY_CHARGE_FROM_GRID and d.battery_kw > 0,
      f"action={d.action.value} battery_kw={d.battery_kw}")

# Narrow spread -> refuses to cycle the battery for a loss.
d = brain.decide(mk_input(base=27, devices=[], tariff=0.26, peak=0.28, offpeak=0.26))
check("Does NOT pre-charge when spread < losses + wear",
      d.action == GridAction.GRID_IMPORT and d.battery_kw == 0, f"action={d.action.value}")
check("Reason honestly explains the refusal",
      "losses+wear" in d.reason, d.reason)

# ── 3. MIN-RUNTIME / ANTI SHORT-CYCLE ────────────────────────────────────────
print("\n3) MIN-RUNTIME LOCKS")

# Just switched OFF -> can't restart even though it's off-peak.
dev = mk_dev("ev", 11, is_on=False, min_off=10, last_change=NOW)
d = brain.decide(mk_input(base=27, devices=[dev], tariff=0.12))
check("Locked-off device stays off despite a cheap window",
      not d.device_commands["ev"], d.device_commands)

# Just switched ON -> can't stop yet even though it's peak with no surplus.
dev = mk_dev("ev", 11, is_on=True, min_on=10, last_change=NOW)
d = brain.decide(mk_input(base=90, devices=[dev], tariff=0.28))
check("Locked-on device keeps running despite peak prices",
      d.device_commands["ev"], d.device_commands)

# Lock expired -> free to switch off now.
dev = mk_dev("ev", 11, is_on=True, min_on=10, last_change=NOW - timedelta(minutes=20))
d = brain.decide(mk_input(base=90, devices=[dev], tariff=0.28))
check("Once the min-on time has elapsed, it can switch off",
      not d.device_commands["ev"], d.device_commands)

# A deadline beats the lock (equipment protection yields to a missed task).
dev = mk_dev("ev", 20, is_on=False, min_off=10, last_change=NOW, kwh=10, hours_deadline=0.1)
d = brain.decide(mk_input(base=27, devices=[dev], tariff=0.28))
check("Must-run overrides an off-lock (deadline wins)",
      d.device_commands["ev"], d.device_commands)

# ── summary ──────────────────────────────────────────────────────────────────
print("\n" + "=" * 60)
print(f"  RESULT: {_passed} passed, {_failed} failed")
print("=" * 60)
raise SystemExit(1 if _failed else 0)
