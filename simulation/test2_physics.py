"""
TEST 2 — Does the engine obey physics?

Run ONE clear day through the baseline controller and print the hourly table.
Then verify the single most important property: ENERGY IS CONSERVED every hour.

    solar + grid_import + battery_discharge  ==  load + battery_charge + grid_export

If this fails, every euro figure later is fiction. So we check it first.
"""

import factory as F
from engine import simulate
from controllers import reactive


def main():
    print("=" * 70)
    print("TEST 2 — ENERGY BALANCE (one clear day, baseline controller)")
    print("=" * 70)

    day = [F.DayWeather(cloud_factor=0.1)]  # one near-clear day
    totals = simulate(day, reactive)

    print(f"\n{'hr':>3} {'solar':>6} {'load':>6} {'batt':>7} {'import':>7} "
          f"{'export':>7} {'soc%':>5} {'cost€':>7}  balance")
    print("-" * 70)

    max_err = 0.0
    for r in totals.steps:
        charge = max(r.battery_ac_kwh, 0)
        discharge = max(-r.battery_ac_kwh, 0)
        # Energy in == energy out ?
        left = r.solar_kwh + r.grid_import_kwh + discharge
        right = r.load_kwh + charge + r.grid_export_kwh
        err = abs(left - right)
        max_err = max(max_err, err)
        soc_pct = r.soc_kwh / F.BATTERY_CAPACITY_KWH * 100
        # Tolerance = 1e-3 because table values are rounded to 3 decimals.
        print(f"{r.hour:>3} {r.solar_kwh:>6.1f} {r.load_kwh:>6.1f} "
              f"{r.battery_ac_kwh:>+7.1f} {r.grid_import_kwh:>7.1f} "
              f"{r.grid_export_kwh:>7.1f} {soc_pct:>5.0f} {r.cost_eur:>7.2f}  "
              f"{'OK' if err < 1e-3 else f'ERR {err:.4f}'}")

    print("-" * 70)
    print(f"\n[OUTPUT] Day totals:")
    print(f"  Grid imported ............. {totals.grid_import_kwh:8.1f} kWh")
    print(f"  Grid exported ............. {totals.grid_export_kwh:8.1f} kWh")
    print(f"  Solar produced ............ {totals.solar_total_kwh:8.1f} kWh")
    print(f"  Load served ............... {totals.load_kwh:8.1f} kWh")
    print(f"  Day electricity cost ...... {totals.cost_eur:8.2f} EUR")
    print(f"  CO2 emitted ............... {totals.co2_kg:8.1f} kg")

    print(f"\n[SANITY CHECK]")
    # 1e-3 tolerance: display values are rounded to 3 decimals (0.001 kWh).
    print(f"  [{'PASS' if max_err < 1e-3 else 'FAIL'}] "
          f"Energy conserved every hour (max error {max_err:.2e} kWh = display rounding)")
    # Baseline battery should barely move (no solar surplus exists)
    battery_moved = sum(abs(r.battery_ac_kwh) for r in totals.steps)
    print(f"  [INFO] Total battery movement: {battery_moved:.1f} kWh "
          f"(near 0 = dumb controller leaves battery idle)")


if __name__ == "__main__":
    main()
