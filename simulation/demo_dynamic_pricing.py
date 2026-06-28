"""
DEMO — why optimal control matters: DYNAMIC hourly pricing.

On a flat peak/off-peak tariff, hand rules ≈ optimal (Test 5: €12/mo gap).
But real industrial tariffs are increasingly DYNAMIC — the price changes every
hour with the spot market: morning and evening peaks, a midday crash when solar
floods the grid, all shifting with the weather day to day.

A human can't hand-tune rules for that. The LP optimiser just solves it.

Both strategies below use the identical validated battery physics
(engine._apply_battery), the identical prices, and export at the spot price
(as real dynamic tariffs do). Only the decision logic differs.
"""

import math
import random
import time

import factory as F
from engine import _apply_battery, HORIZON_HOURS
from optimizer import optimal_battery_schedule

START_SOC = 0.10 * F.BATTERY_CAPACITY_KWH

# Price model lives in factory.py (it's an input). Alias for this script's use.
dynamic_prices = F.dynamic_price_series
export_prices = F.export_price_series


def run(strategy, solar, load, prices, feed_in):
    """Step through with strategy(t, soc)->battery_ac. Returns (cost, grid_import)."""
    soc = START_SOC
    cost = 0.0
    grid_import = 0.0
    for t in range(len(solar)):
        ac, soc = _apply_battery(soc, strategy(t, soc))
        net = load[t] - solar[t] + ac
        gi = max(net, 0.0)
        ge = max(-net, 0.0)
        cost += gi * prices[t] - ge * feed_in[t]
        grid_import += gi
    return cost, grid_import


# ── Strategy: sensible hand-written threshold rule ───────────────────────────
def make_rule(prices):
    def rule(t, soc):
        day = prices[(t // 24) * 24:(t // 24) * 24 + 24]
        avg = sum(day) / len(day)
        p = prices[t]
        if p < avg * 0.85:
            return F.BATTERY_MAX_CHARGE_KW
        if p > avg * 1.15:
            return -F.BATTERY_MAX_DISCHARGE_KW
        return 0.0
    return rule


# ── Strategy: LP-MPC optimiser ───────────────────────────────────────────────
def make_optimal(solar, load, prices, feed_in):
    n = len(solar)
    def opt(t, soc):
        end = min(t + HORIZON_HOURS, n)
        sched = optimal_battery_schedule(solar[t:end], load[t:end], prices[t:end],
                                         feed_in[t:end], soc, terminal_value=0.0)
        if sched is None:
            return solar[t] - load[t]
        return float(sched["charge"][0] - sched["discharge"][0])
    return opt


def main():
    print("=" * 70)
    print("DEMO — DYNAMIC HOURLY PRICING:  hand rule  vs  LP optimiser")
    print("=" * 70)

    weather = F.generate_month_weather(days=30, seed=42)
    solar = [day.solar_kwh(h) for day in weather for h in range(24)]
    load = [F.LOAD_PROFILE_KW[h] for _ in weather for h in range(24)]
    prices = dynamic_prices(weather)
    feed_in = export_prices(prices)

    print(f"\n[INPUT] Dynamic price (€/kWh) — sample day 1 (note midday crash, evening spike):")
    line = "   "
    for h in range(24):
        line += f"{prices[h]:.2f} "
        if h == 11:
            line += "\n   "
    print(line)
    print(f"  range {min(prices):.2f}–{max(prices):.2f}, avg {sum(prices)/len(prices):.3f} €/kWh")

    # Fair reference: same solar, but battery sits idle (null strategy).
    ref_cost, _ = run(lambda t, soc: 0.0, solar, load, prices, feed_in)
    rule_cost, _ = run(make_rule(prices), solar, load, prices, feed_in)

    t0 = time.time()
    opt_cost, _ = run(make_optimal(solar, load, prices, feed_in), solar, load, prices, feed_in)
    opt_time = time.time() - t0

    print(f"\n[OUTPUT] Monthly cost under dynamic prices (solar in all cases):")
    print(f"  {'Strategy':<28}{'Cost €':>10}{'vs idle €':>11}{'% saved':>9}")
    print(f"  {'-'*58}")
    print(f"  {'battery idle (reference)':<28}{ref_cost:>10.0f}{0:>11.0f}{0:>9.1f}")
    for name, cost in [("hand rule (threshold)", rule_cost), ("LP optimiser (MPC)", opt_cost)]:
        saved = ref_cost - cost
        print(f"  {name:<28}{cost:>10.0f}{saved:>11.0f}{saved/ref_cost*100:>9.1f}")

    edge = rule_cost - opt_cost
    print(f"\n[RESULT]  (optimiser solved 720 rolling plans in {opt_time:.1f}s)")
    print(f"  Hand rule saves    €{ref_cost-rule_cost:,.0f}/month vs idle battery.")
    print(f"  LP optimiser saves €{ref_cost-opt_cost:,.0f}/month — €{edge:,.0f} MORE than the rule")
    print(f"  ({edge/(ref_cost-rule_cost)*100:.0f}% more savings), with zero hand-tuning.")
    print(f"\n  This is the case for optimal control: as tariffs get complex,")
    print(f"  rules fall behind and the optimiser pulls ahead automatically.")


if __name__ == "__main__":
    main()
