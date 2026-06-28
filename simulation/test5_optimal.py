"""
TEST 5 — Optimal control (LP-MPC) vs rules vs reactive.

Three controllers, same factory, same month, same hardware:
  reactive    — dumb: react to right-now surplus/deficit
  predictive  — my hand-written rules (off-peak charge, peak discharge)
  optimal     — Linear-Program MPC: computes the cheapest schedule itself

We expect: optimal cost <= predictive cost <= reactive cost.
The optimal controller is PROVABLY the best any controller could do given the
same forecast — it's the ceiling on how much money the software can save.
"""

import time
import factory as F
from engine import simulate
from controllers import reactive, predictive
from optimizer import optimal


def peak_import(t):
    return sum(r.grid_import_kwh for r in t.steps if F.is_peak(r.hour))


def energy_balance_ok(t):
    worst = 0.0
    for r in t.steps:
        charge = max(r.battery_ac_kwh, 0)
        discharge = max(-r.battery_ac_kwh, 0)
        left = r.solar_kwh + r.grid_import_kwh + discharge
        right = r.load_kwh + charge + r.grid_export_kwh
        worst = max(worst, abs(left - right))
    return worst


def main():
    print("=" * 72)
    print("TEST 5 — OPTIMAL (LP-MPC) vs RULES vs REACTIVE  (30-day month)")
    print("=" * 72)

    weather = F.generate_month_weather(days=30, seed=42)

    runs = {}
    for name, ctrl in [("reactive", reactive), ("predictive (rules)", predictive),
                       ("optimal (LP-MPC)", optimal)]:
        t0 = time.time()
        runs[name] = simulate(weather, ctrl)
        dt = time.time() - t0
        print(f"  ran {name:<22} in {dt:5.2f}s")

    base = runs["reactive"].cost_eur

    print(f"\n[OUTPUT] Monthly comparison:")
    print(f"  {'Controller':<22}{'Cost €':>10}{'Saved €':>10}{'% bill':>8}{'Peak MWh':>10}")
    print(f"  {'-'*60}")
    for name, t in runs.items():
        saved = base - t.cost_eur
        pct = saved / base * 100
        print(f"  {name:<22}{t.cost_eur:>10.0f}{saved:>10.0f}{pct:>8.1f}{peak_import(t)/1000:>10.2f}")

    opt = runs["optimal (LP-MPC)"]
    rules = runs["predictive (rules)"]
    extra = rules.cost_eur - opt.cost_eur

    print(f"\n[VERIFY]")
    bal = energy_balance_ok(opt)
    print(f"  [{'PASS' if bal < 2e-3 else 'FAIL'}] Optimal run conserves energy "
          f"(max err {bal:.2e} kWh)")
    print(f"  [{'PASS' if opt.cost_eur <= rules.cost_eur + 1e-6 else 'FAIL'}] "
          f"Optimal is at least as cheap as the rules")
    print(f"  [{'PASS' if opt.cost_eur <= base else 'FAIL'}] "
          f"Optimal beats reactive baseline")

    print(f"\n[RESULT]")
    print(f"  Optimal saves €{base-opt.cost_eur:,.0f}/month "
          f"({(base-opt.cost_eur)/base*100:.1f}% of the bill).")
    print(f"  That's €{extra:,.0f}/month MORE than my hand-written rules —")
    print(f"  and it needed zero tuning. It just solved for the best plan.")


if __name__ == "__main__":
    main()
