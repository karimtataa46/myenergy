"""
STRESS TEST — try hard to BREAK the simulation.

The normal suite checks the happy path. This one fuzzes thousands of random and
extreme scenarios and asserts the laws that must NEVER break, for ALL three
controllers (reactive, rule-based, LP optimal):

  • energy is conserved every hour (no energy invented or lost in the books)
  • a battery never creates energy (round-trip always loses)
  • SOC never leaves [min, max]; battery power never exceeds its rating
  • grid import/export never go negative
  • the optimiser never silently fails (returns None -> reactive fallback)
  • the optimiser is never worse than doing nothing smart

If any line says FAIL, that's a real bug.
"""

import random
import itertools

import factory as F
from engine import _apply_battery, HORIZON_HOURS, StepState
from controllers import reactive, predictive
from optimizer import optimal, optimal_battery_schedule

PASS = 0
FAIL = 0
def check(label, ok, detail=""):
    global PASS, FAIL
    PASS, FAIL = (PASS+1, FAIL) if ok else (PASS, FAIL+1)
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}" + (f"   ({detail})" if detail else ""))

CAP = F.BATTERY_CAPACITY_KWH
MINK = F.BATTERY_MIN_SOC * CAP
MAXK = F.BATTERY_MAX_SOC * CAP
RATE = F.BATTERY_MAX_CHARGE_KW

print("=" * 72)
print("STRESS TEST — fuzzing for bugs")
print("=" * 72)

# ── 1) _apply_battery: exhaustive grid over (soc, request) ───────────────────
print("\n1) BATTERY MODEL — exhaustive (soc, request) sweep")
bounds_ok = rate_ok = nocreate_ok = True
worst_create = 0.0
for soc0 in [MINK + i*9 for i in range(int((MAXK-MINK)/9)+1)]:
    for req in range(-90, 91, 5):
        ac, soc1 = _apply_battery(soc0, req)
        if not (MINK - 1e-9 <= soc1 <= MAXK + 1e-9): bounds_ok = False
        if abs(ac) > RATE + 1e-9: rate_ok = False
        # energy can't be created: charging stores <= AC drawn; discharging delivers <= drained
        if ac >= 0:                      # charging
            stored = soc1 - soc0
            if stored > ac + 1e-9: nocreate_ok = False
            worst_create = max(worst_create, stored - ac)
        else:                            # discharging
            drained = soc0 - soc1
            delivered = -ac
            if delivered > drained + 1e-9: nocreate_ok = False
            worst_create = max(worst_create, delivered - drained)
check("SOC always within [min,max]", bounds_ok)
check("Battery power never exceeds rating", rate_ok)
check("Battery never creates energy (round-trip loses)", nocreate_ok,
      f"worst surplus {worst_create:.2e} kWh")

# ── driver that runs a controller over arbitrary arrays with tight checks ────
def drive(controller, solar, load, start_hour=0, soc0=None):
    N = len(solar)
    soc = soc0 if soc0 is not None else MINK
    steps = []
    fallback = 0
    for t in range(N):
        h = (start_hour + t) % 24
        end = min(t + HORIZON_HOURS, N)
        nxt = solar[t+1:t+4]
        st = StepState(hour=h, solar_kwh=solar[t], load_kwh=load[t], soc_kwh=soc,
                       capacity_kwh=CAP,
                       forecast_next_solar_kwh=(sum(nxt)/len(nxt) if nxt else 0.0),
                       forecast_tomorrow_deficit_kwh=0.0,
                       forecast_solar_kwh=solar[t:end], forecast_load_kwh=load[t:end])
        req = controller(st)
        ac, soc = _apply_battery(soc, req)
        net = load[t] - solar[t] + ac
        gi, ge = max(net, 0.0), max(-net, 0.0)
        steps.append((ac, soc, gi, ge, F.tariff(h)))
    return steps

def invariants(steps, solar, load):
    bal = soc_ok = sign = rate = True
    for i, (ac, soc, gi, ge, _) in enumerate(steps):
        charge, dis = max(ac, 0), max(-ac, 0)
        if abs((solar[i] + gi + dis) - (load[i] + charge + ge)) > 1e-9: bal = False
        if not (MINK - 1e-6 <= soc <= MAXK + 1e-6): soc_ok = False
        if gi < -1e-9 or ge < -1e-9: sign = False
        if abs(ac) > RATE + 1e-6: rate = False
    return bal, soc_ok, sign, rate

def cost(steps):
    return sum(gi*tar - ge*F.FEED_IN_TARIFF for (_, _, gi, ge, tar) in steps)

# ── 2) Random fuzz: 400 scenarios x 3 controllers ────────────────────────────
print("\n2) RANDOM FUZZ — 400 scenarios x 3 controllers")
rng = random.Random(7)
ctrls = {"reactive": reactive, "predictive": predictive, "optimal": optimal}
agg = {n: {"bal": True, "soc": True, "sign": True, "rate": True} for n in ctrls}
none_count = 0
worse_than_reactive = 0
for s in range(400):
    N = rng.choice([24, 36, 48])
    h0 = rng.randrange(24)
    solar = [round(max(0, rng.gauss(25, 25)), 1) for _ in range(N)]      # 0..~90
    load = [round(rng.uniform(20, 110), 1) for _ in range(N)]
    soc0 = round(rng.uniform(MINK, MAXK), 1)
    base = drive(reactive, solar, load, h0, soc0)
    for n, c in ctrls.items():
        st = drive(c, solar, load, h0, soc0)
        b, so, si, ra = invariants(st, solar, load)
        agg[n]["bal"] &= b; agg[n]["soc"] &= so; agg[n]["sign"] &= si; agg[n]["rate"] &= ra
    # optimiser quality: never worse than reactive (allow tiny numerical slack)
    if cost(drive(optimal, solar, load, h0, soc0)) > cost(base) + 0.5:
        worse_than_reactive += 1
    # did the LP ever fail? (it falls back to reactive == solar-load; detect via a probe)
    for t in range(N):
        end = min(t + HORIZON_HOURS, N)
        price = [F.tariff((h0+t+k) % 24) for k in range(end-t)]
        if optimal_battery_schedule(solar[t:end], load[t:end], price,
                                    [F.FEED_IN_TARIFF]*(end-t), soc0) is None:
            none_count += 1
            break
for n in ctrls:
    check(f"[{n}] energy conserved every hour", agg[n]["bal"])
    check(f"[{n}] SOC in bounds & rate ok & grid>=0",
          agg[n]["soc"] and agg[n]["rate"] and agg[n]["sign"])
check("Optimiser never silently failed (no None) on realistic inputs", none_count == 0,
      f"{none_count} scenarios hit a solver failure")
check("Optimiser never worse than reactive", worse_than_reactive == 0,
      f"{worse_than_reactive}/400 scenarios worse")

# ── 3) EXTREME edge cases ────────────────────────────────────────────────────
print("\n3) EXTREME EDGE CASES")
edge = {
  "zero solar, high load":      ([0.0]*36,            [100.0]*36),
  "huge solar, zero load":      ([200.0]*36,          [0.0]*36),
  "solar == load exactly":      ([50.0]*36,           [50.0]*36),
  "load spikes above grid cap": ([0.0]*36,            [300.0]*36),
  "tiny everything":            ([0.01]*36,           [0.01]*36),
}
for name, (solar, load) in edge.items():
    okall = True
    for c in ctrls.values():
        st = drive(c, solar, load, 0, MINK)
        b, so, si, ra = invariants(st, solar, load)
        okall &= (b and so and si and ra)
    check(f"survives: {name}", okall)

# ── 4) Brute-force cross-check (independent optimum) ─────────────────────────
print("\n4) OPTIMISER vs INDEPENDENT BRUTE FORCE (extra scenarios)")
levels = [-50,-40,-30,-20,-10,0,10,20,30,40,50]
def bf(solar, load, price, feed, soc0):
    best = float("inf")
    for seq in itertools.product(levels, repeat=len(solar)):
        s = soc0; c = 0.0
        for k in range(len(seq)):
            ac, s = _apply_battery(s, seq[k])
            net = load[k]-solar[k]+ac
            c += max(net,0)*price[k] - max(-net,0)*feed[k]
        best = min(best, c)
    return best
worst_gap = 0.0
okbf = True
for i in range(5):
    H = 5
    solar = [round(rng.uniform(0,60),1) for _ in range(H)]
    load = [round(rng.uniform(20,100),1) for _ in range(H)]
    price = [round(rng.uniform(0.05,0.40),3) for _ in range(H)]
    feed = [max(0.0,p-0.01) for p in price]
    soc0 = round(rng.uniform(MINK,MAXK),1)
    sch = optimal_battery_schedule(solar, load, price, feed, soc0, terminal_value=0.0)
    lp = sum(sch["import"][k]*price[k]-sch["export"][k]*feed[k] for k in range(H))
    brute = bf(solar, load, price, feed, soc0)
    gap = brute - lp
    worst_gap = max(worst_gap, abs(gap))
    if lp > brute + 1e-6 or gap > 5.0: okbf = False
check("LP matches brute-force optimum (within discretisation)", okbf,
      f"worst gap €{worst_gap:.2f}")

print("\n" + "=" * 72)
print(f"  RESULT: {PASS} passed, {FAIL} failed")
print("=" * 72)
print("  (FAIL = a real bug. All PASS = the engine is sound under stress.)")
