"""
VERIFY — does the simulation's inputs & outputs actually behave correctly?

This is not a demo. It asserts the simulation against:
  A) INPUT validation      — the facts fed in are well-formed
  B) KNOWN-ANSWER tests    — results we can compute BY HAND must match exactly
  C) PHYSICS invariants    — laws that must hold every hour, all month, both controllers
  D) OUTPUT sanity         — the results are internally consistent

If any line says FAIL, the euro figures cannot be trusted. All must PASS.
"""

import factory as F
from engine import simulate, step, _apply_battery, StepState
from controllers import reactive, predictive

PASS = 0
FAIL = 0


def check(label, ok, detail=""):
    global PASS, FAIL
    tag = "PASS" if ok else "FAIL"
    if ok:
        PASS += 1
    else:
        FAIL += 1
    print(f"  [{tag}] {label}" + (f"   ({detail})" if detail else ""))


def approx(a, b, tol=1e-6):
    return abs(a - b) <= tol


class ZeroSolarDay:
    """A day with literally zero solar — lets us hand-compute the answer."""
    cloud_factor = 1.0
    def solar_kwh(self, hour):
        return 0.0


# ─────────────────────────────────────────────────────────────────────────────
print("=" * 70)
print("VERIFY SIMULATION — inputs & outputs")
print("=" * 70)

# ── A) INPUT VALIDATION ──────────────────────────────────────────────────────
print("\nA) INPUT VALIDATION")

check("Load profile has 24 hourly values", len(F.LOAD_PROFILE_KW) == 24,
      f"len={len(F.LOAD_PROFILE_KW)}")
check("All load values positive", all(v > 0 for v in F.LOAD_PROFILE_KW))
check("Peak load is 100 kW", F.peak_load_kw() == 100.0, f"{F.peak_load_kw()} kW")
check("Daily load sums to 1564 kWh", approx(F.daily_load_kwh(), 1564.0),
      f"{F.daily_load_kwh()} kWh")

check("Solar is 0 before sunrise (03:00)", F.clear_sky_kw(3) == 0.0)
check("Solar is 0 after sunset (22:00)", F.clear_sky_kw(22) == 0.0)
check("Solar peaks at midday (13:00) > 0", F.clear_sky_kw(13) > 0)
check("Solar never exceeds array peak",
      all(F.clear_sky_kw(h) <= F.SOLAR_PEAK_KW + 1e-9 for h in range(24)))

check("Tariff at 10:00 is PEAK (0.28)", F.tariff(10) == 0.28)
check("Tariff at 03:00 is OFF-PEAK (0.12)", F.tariff(3) == 0.12)
check("Tariff at 21:00 is PEAK (boundary)", F.tariff(21) == 0.28)
check("Tariff at 22:00 is OFF-PEAK (boundary)", F.tariff(22) == 0.12)

w1 = F.generate_month_weather(days=30, seed=42)
w2 = F.generate_month_weather(days=30, seed=42)
check("Weather generator returns 30 days", len(w1) == 30)
check("All cloud factors in [0,1]", all(0 <= d.cloud_factor <= 1 for d in w1))
check("Weather is deterministic (same seed -> same days)",
      all(approx(a.cloud_factor, b.cloud_factor) for a, b in zip(w1, w2)))

# ── B) KNOWN-ANSWER TESTS (hand computed) ────────────────────────────────────
print("\nB) KNOWN-ANSWER TESTS (computed by hand, engine must match)")

# B1: No solar, battery untouched -> cost is just load x tariff, hour by hour.
#     Off-peak load (h 0-6,22,23) = 294 kWh x 0.12 = 35.28
#     Peak load    (h 7-21)       = 1270 kWh x 0.28 = 355.60
#     => exactly 390.88 EUR/day, 1564 kWh imported.
null_controller = lambda s: 0.0
t = simulate([ZeroSolarDay()], null_controller, start_soc_kwh=20.0)
check("Zero-solar day cost == 390.88 EUR (hand-computed)",
      approx(t.cost_eur, 390.88, tol=0.01), f"got {t.cost_eur}")
check("Zero-solar day grid import == 1564 kWh",
      approx(t.grid_import_kwh, 1564.0, tol=0.01), f"got {t.grid_import_kwh}")
check("Zero-solar day battery never moved",
      approx(sum(abs(r.battery_ac_kwh) for r in t.steps), 0.0))

# B2: Battery charge efficiency. From 20 kWh, request +50 kWh AC.
#     stored = 50 * 0.95 = 47.5  ->  new soc = 67.5
ac, soc = _apply_battery(20.0, 50.0)
check("Charge +50: AC accepted == 50", approx(ac, 50.0), f"ac={ac}")
check("Charge +50: stored at 0.95 eff -> soc 67.5", approx(soc, 67.5), f"soc={soc}")

# B3: Battery discharge efficiency + reserve floor.
#     From 67.5 kWh, request -50 AC. Want 50 out -> need 52.63 from cells,
#     but only 67.5-20(reserve)=47.5 available -> delivered = 47.5*0.95 = 45.125
ac, soc = _apply_battery(67.5, -50.0)
check("Discharge -50 hits reserve: delivered == 45.125",
      approx(-ac, 45.125, tol=1e-3), f"delivered={-ac:.3f}")
check("Discharge stops exactly at 10% reserve (20 kWh)", approx(soc, 20.0, tol=1e-3),
      f"soc={soc:.3f}")

# B4: Rate limiting. Request a huge charge -> clamp to 50 kW.
ac, soc = _apply_battery(100.0, 999.0)
check("Charge request 999 clamped to 50 kW rate", approx(ac, 50.0), f"ac={ac}")

# B5: Full battery can't overcharge. From 190 kWh (95%), request +50.
#     room = 200-190 = 10 stored -> ac = 10/0.95 = 10.526
ac, soc = _apply_battery(190.0, 50.0)
check("Near-full battery caps charge at capacity", approx(soc, 200.0, tol=1e-3),
      f"soc={soc:.3f}")

# ── C) PHYSICS INVARIANTS (full month, BOTH controllers) ─────────────────────
print("\nC) PHYSICS INVARIANTS (30 days, both controllers)")

weather = F.generate_month_weather(days=30, seed=42)
for name, ctrl in [("reactive", reactive), ("predictive", predictive)]:
    res = simulate(weather, ctrl)
    cap = F.BATTERY_CAPACITY_KWH
    min_kwh, max_kwh = F.BATTERY_MIN_SOC * cap, F.BATTERY_MAX_SOC * cap

    max_balance_err = 0.0
    soc_ok = True
    rate_ok = True
    sign_ok = True
    for r in res.steps:
        charge = max(r.battery_ac_kwh, 0)
        discharge = max(-r.battery_ac_kwh, 0)
        left = r.solar_kwh + r.grid_import_kwh + discharge
        right = r.load_kwh + charge + r.grid_export_kwh
        max_balance_err = max(max_balance_err, abs(left - right))
        if not (min_kwh - 1e-6 <= r.soc_kwh <= max_kwh + 1e-6):
            soc_ok = False
        if abs(r.battery_ac_kwh) > F.BATTERY_MAX_CHARGE_KW + 1e-6:
            rate_ok = False
        if r.grid_import_kwh < -1e-9 or r.grid_export_kwh < -1e-9:
            sign_ok = False

    print(f"  -- {name} --")
    check(f"[{name}] Energy conserved every hour (<2e-3)",
          max_balance_err < 2e-3, f"max err {max_balance_err:.2e} kWh")
    check(f"[{name}] SOC stays within [10%, 100%] = [20,200] kWh", soc_ok)
    check(f"[{name}] Battery rate <= 50 kW every hour", rate_ok)
    check(f"[{name}] Grid import/export never negative", sign_ok)
    check(f"[{name}] Solar fraction in [0,1]",
          0 <= res.solar_fraction <= 1, f"{res.solar_fraction:.3f}")

# ── D) OUTPUT SANITY ─────────────────────────────────────────────────────────
print("\nD) OUTPUT SANITY")

base = simulate(weather, reactive)
smart = simulate(weather, predictive)
base2 = simulate(weather, reactive)

check("Deterministic: same inputs -> identical cost",
      approx(base.cost_eur, base2.cost_eur), f"{base.cost_eur} vs {base2.cost_eur}")
check("myEnergy never costs MORE than baseline",
      smart.cost_eur <= base.cost_eur,
      f"smart {smart.cost_eur} <= base {base.cost_eur}")
check("Both serve the SAME load (apples-to-apples)",
      approx(base.load_kwh, smart.load_kwh), f"{base.load_kwh} kWh")
check("Saving is positive", base.cost_eur - smart.cost_eur > 0,
      f"saved EUR {base.cost_eur - smart.cost_eur:.2f}")
peak_base = sum(r.grid_import_kwh for r in base.steps if F.is_peak(r.hour))
peak_smart = sum(r.grid_import_kwh for r in smart.steps if F.is_peak(r.hour))
check("Peak-window import: myEnergy < baseline",
      peak_smart < peak_base, f"{peak_smart:.0f} < {peak_base:.0f} kWh")

# ── SUMMARY ──────────────────────────────────────────────────────────────────
print("\n" + "=" * 70)
print(f"  RESULT:  {PASS} passed, {FAIL} failed")
print("=" * 70)
if FAIL == 0:
    print("  All checks passed — inputs validated, outputs match hand math,")
    print("  physics holds for both controllers. The euro figures are trustworthy.")
else:
    print("  SOMETHING IS WRONG — do not trust the savings number until fixed.")
