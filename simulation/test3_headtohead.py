"""
TEST 3 — Baseline vs myEnergy on ONE day, same hardware.

This is the heart of the product. We run both controllers through an
identical day and show, hour by hour, where myEnergy makes a different
(cheaper) decision.
"""

import factory as F
from engine import simulate
from controllers import reactive, predictive


def run_one_day(cloud: float):
    day = [F.DayWeather(cloud_factor=cloud)]
    base = simulate(day, reactive)
    smart = simulate(day, predictive)
    return base, smart


def main():
    print("=" * 78)
    print("TEST 3 — BASELINE vs myENERGY  (one partly-cloudy day, same hardware)")
    print("=" * 78)

    cloud = 0.4
    base, smart = run_one_day(cloud)

    print(f"\n{'hr':>3} {'tariff':>6} │ {'BASELINE':>18} │ {'myENERGY':>18} │ decision")
    print(f"{'':>3} {'€/kWh':>6} │ {'batt':>7} {'import':>9} │ {'batt':>7} {'import':>9} │")
    print("-" * 78)

    for hb, hs in zip(base.steps, smart.steps):
        t = F.tariff(hb.hour)
        tag = ""
        if hs.battery_ac_kwh < -0.1 and hb.battery_ac_kwh > -0.1:
            tag = "discharge on peak ↓"
        elif hs.battery_ac_kwh > 0.1 and hb.battery_ac_kwh < 0.1:
            tag = "charge cheap night ↑"
        print(f"{hb.hour:>3} {t:>6.2f} │ {hb.battery_ac_kwh:>+7.1f} {hb.grid_import_kwh:>9.1f} │ "
              f"{hs.battery_ac_kwh:>+7.1f} {hs.grid_import_kwh:>9.1f} │ {tag}")

    print("-" * 78)
    saving = base.cost_eur - smart.cost_eur
    print(f"\n[OUTPUT] One-day result (cloud={cloud}):")
    print(f"  {'Metric':<26}{'Baseline':>12}{'myEnergy':>12}{'Δ':>12}")
    print(f"  {'-'*60}")
    print(f"  {'Cost (EUR)':<26}{base.cost_eur:>12.2f}{smart.cost_eur:>12.2f}"
          f"{saving:>12.2f}")
    print(f"  {'Grid import (kWh)':<26}{base.grid_import_kwh:>12.1f}"
          f"{smart.grid_import_kwh:>12.1f}{smart.grid_import_kwh-base.grid_import_kwh:>12.1f}")
    print(f"  {'Peak-hour import (kWh)':<26}{_peak_import(base):>12.1f}"
          f"{_peak_import(smart):>12.1f}{_peak_import(smart)-_peak_import(base):>12.1f}")
    print(f"  {'CO2 (kg)':<26}{base.co2_kg:>12.1f}{smart.co2_kg:>12.1f}"
          f"{smart.co2_kg-base.co2_kg:>12.1f}")

    print(f"\n[WHERE THE MONEY COMES FROM]")
    print(f"  myEnergy shifts {_peak_import(base)-_peak_import(smart):.0f} kWh of grid use")
    print(f"  out of the €{F.PEAK_TARIFF:.2f} peak window into the €{F.OFFPEAK_TARIFF:.2f} night window,")
    print(f"  using the battery the baseline left idle.")
    print(f"\n  >>> One day saving: €{saving:.2f}  ({saving/base.cost_eur*100:.1f}% of the bill)")


def _peak_import(totals):
    return sum(r.grid_import_kwh for r in totals.steps if F.is_peak(r.hour))


if __name__ == "__main__":
    main()
