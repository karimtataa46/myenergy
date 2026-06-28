"""
TEST 4 — A full realistic month. THE "is it worth it?" number.

30 days of mixed weather (sunny / cloudy / overcast), same hardware,
baseline vs myEnergy. We report monthly euros saved and annualise it.
"""

import factory as F
from engine import simulate
from controllers import reactive, predictive


def main():
    print("=" * 70)
    print("TEST 4 — FULL MONTH: BASELINE vs myENERGY")
    print("=" * 70)

    weather = F.generate_month_weather(days=30, seed=42)

    sunny = sum(1 for w in weather if w.cloud_factor < 0.25)
    partly = sum(1 for w in weather if 0.25 <= w.cloud_factor < 0.60)
    overcast = sum(1 for w in weather if w.cloud_factor >= 0.60)
    print(f"\n[INPUT] 30-day weather mix:")
    print(f"  Sunny days ......... {sunny}")
    print(f"  Partly cloudy ...... {partly}")
    print(f"  Overcast ........... {overcast}")

    base = simulate(weather, reactive)
    smart = simulate(weather, predictive)
    saving = base.cost_eur - smart.cost_eur

    print(f"\n[OUTPUT] Monthly results:")
    print(f"  {'Metric':<28}{'Baseline':>12}{'myEnergy':>12}{'Δ':>12}")
    print(f"  {'-'*64}")
    print(f"  {'Electricity cost (EUR)':<28}{base.cost_eur:>12.0f}"
          f"{smart.cost_eur:>12.0f}{saving:>12.0f}")
    print(f"  {'Grid import (MWh)':<28}{base.grid_import_kwh/1000:>12.2f}"
          f"{smart.grid_import_kwh/1000:>12.2f}"
          f"{(smart.grid_import_kwh-base.grid_import_kwh)/1000:>12.2f}")
    print(f"  {'Peak-window import (MWh)':<28}{_peak(base)/1000:>12.2f}"
          f"{_peak(smart)/1000:>12.2f}{(_peak(smart)-_peak(base))/1000:>12.2f}")
    print(f"  {'Solar self-use (%)':<28}{base.solar_fraction*100:>12.1f}"
          f"{smart.solar_fraction*100:>12.1f}"
          f"{(smart.solar_fraction-base.solar_fraction)*100:>12.1f}")
    print(f"  {'CO2 emitted (kg)':<28}{base.co2_kg:>12.0f}{smart.co2_kg:>12.0f}"
          f"{smart.co2_kg-base.co2_kg:>12.0f}")

    pct = saving / base.cost_eur * 100
    print(f"\n{'='*70}")
    print(f"  MONTHLY SAVING:   €{saving:,.0f}   ({pct:.1f}% of the bill)")
    print(f"  ANNUALISED:       €{saving*12:,.0f}/year  (same hardware, software only)")
    print(f"{'='*70}")

    print(f"\n[IS IT WORTH IT?]")
    sub = 150  # assumed monthly software subscription
    print(f"  If myEnergy costs ~€{sub}/month, net gain = €{saving-sub:,.0f}/month")
    print(f"  Payback on the software is immediate; it pays for itself "
          f"{saving/sub:.1f}x over.")
    print(f"\n  NOTE: this is a spring/summer month. Winter solar is lower, but the")
    print(f"  arbitrage saving (night->peak) barely depends on solar, so the bulk")
    print(f"  of the saving holds year-round.")


def _peak(totals):
    return sum(r.grid_import_kwh for r in totals.steps if F.is_peak(r.hour))


if __name__ == "__main__":
    main()
