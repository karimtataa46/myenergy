"""
DEBUG — why did the rolling LP lose to the rule? Diagnose the terminal-value term.

Ground truth: solve ONE LP over the whole 7-day window (perfect global optimum).
No controller can beat this. Then compare:
  - the hand rule
  - the rolling-horizon MPC at several terminal-value settings
The rolling MPC should approach the global optimum, and MUST beat the rule.
"""

import factory as F
from engine import _apply_battery, HORIZON_HOURS
from optimizer import optimal_battery_schedule
from demo_dynamic_pricing import dynamic_prices, export_prices, run, make_rule

DAYS = 7
weather = F.generate_month_weather(days=DAYS, seed=42)
solar = [day.solar_kwh(h) for day in weather for h in range(24)]
load = [F.LOAD_PROFILE_KW[h] for _ in weather for h in range(24)]
prices = dynamic_prices(weather)
feed_in = export_prices(prices)
N = len(solar)
START_SOC = 0.10 * F.BATTERY_CAPACITY_KWH

# ── Ground truth: one global LP over all N hours ─────────────────────────────
g = optimal_battery_schedule(solar, load, prices, feed_in, START_SOC,
                             terminal_value=0.0)
global_cost = sum(g["import"][t] * prices[t] - g["export"][t] * feed_in[t] for t in range(N))
print(f"GLOBAL OPTIMUM (one LP over {DAYS} days)  = €{global_cost:8.1f}   <- nothing can beat this")

# ── The hand rule ────────────────────────────────────────────────────────────
rule_cost, _ = run(make_rule(prices), solar, load, prices, feed_in)
print(f"hand rule                                = €{rule_cost:8.1f}")

# ── Rolling MPC at several terminal values ───────────────────────────────────
def rolling(tv):
    def strat(t, soc):
        end = min(t + HORIZON_HOURS, N)
        sched = optimal_battery_schedule(solar[t:end], load[t:end], prices[t:end],
                                         feed_in[t:end], soc, terminal_value=tv)
        if sched is None:
            return solar[t] - load[t]
        return float(sched["charge"][0] - sched["discharge"][0])
    cost, _ = run(strat, solar, load, prices, feed_in)
    return cost

print()
for tv in [0.0, 0.05, 0.10, 0.137, F.OFFPEAK_TARIFF * F.DISCHARGE_EFFICIENCY]:
    print(f"rolling MPC  terminal_value={tv:.3f}      = €{rolling(tv):8.1f}")
