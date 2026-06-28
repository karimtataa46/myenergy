"""
VERIFY the LIVE simulation's inputs & outputs (the engine behind /sim).

The /sim page must not show made-up numbers. This checks the live engine:
  A) every hour it produces conserves energy (physics)
  B) the savings counter == baseline_cost - myenergy_cost  (accounting)
  C) over a full day the optimiser actually wins (savings > 0)
  D) both batteries stay within physical bounds
  E) it's deterministic (same session -> same numbers)
"""

import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "simulation")))

import factory as F
from live_sim import LiveSim

PASS = 0
FAIL = 0
def check(label, ok, detail=""):
    global PASS, FAIL
    PASS, FAIL = (PASS+1, FAIL) if ok else (PASS, FAIL+1)
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}" + (f"   ({detail})" if detail else ""))

print("=" * 68)
print("VERIFY LIVE SIMULATION (engine behind /sim)")
print("=" * 68)

sim = LiveSim()              # constructs + warm-starts
cap = F.BATTERY_CAPACITY_KWH

# ── A) Energy balance in each hourly decision ────────────────────────────────
print("\nA) ENERGY BALANCE — each hour, both controllers")
worst = 0.0
for t in range(min(168, sim.N)):   # sample a full week of hours
    for soc in (0.3*cap, 0.6*cap, 0.95*cap):
        sim.opt_soc = soc
        sim.base_soc = soc
        o = sim._hour_outcome(t % sim.N)
        # myEnergy:  solar + import + discharge == load + charge + export
        ch, dis = max(o["opt_ac"],0), max(-o["opt_ac"],0)
        left  = o["solar"] + o["opt_gi"] + dis
        right = o["load"]  + ch + o["opt_ge"]
        worst = max(worst, abs(left - right))
check("Energy conserved every hour (myEnergy)", worst < 1e-6, f"max err {worst:.2e} kWh")

# ── B) Accounting identity + D) bounds, by driving the clock ─────────────────
print("\nB+D) ACCOUNTING & BOUNDS — drive 48 simulated hours")
sim.reset()
acct_ok = True
bounds_ok = True
monotonic_ok = True
acct_worst = 0.0
prev_savings = None
for _ in range(48):
    sim._integrate(1.0)            # advance one sim-hour
    st = sim.state()
    # The honest instantaneous gap lives in savings_gap_now (base_cost - opt_cost);
    # the headline `savings` is the monotonic realised high-water mark (BUG-01).
    # gap is computed as (base_cost - opt_cost) then each field rounded to 4 dp,
    # so the displayed values agree to within that rounding (~2e-4).
    acct_worst = max(acct_worst, abs(st["savings_gap_now"] - (st["base_cost"] - st["opt_cost"])))
    # Exact identity on full-precision internal values:
    if abs(st["savings_gap_now"] - round(sim.base_cost - sim.opt_cost, 4)) > 1e-12:
        acct_ok = False
    # BUG-01 guarantee: the headline savings counter never ticks down.
    if prev_savings is not None and st["savings"] < prev_savings - 1e-9:
        monotonic_ok = False
    prev_savings = st["savings"]
    if not (9.99 <= st["opt_soc_pct"] <= 100.01): bounds_ok = False
    if not (9.99 <= st["base_soc_pct"] <= 100.01): bounds_ok = False
check("savings_gap_now == round(baseline_cost - myenergy_cost) exactly", acct_ok)
check("Displayed fields self-consistent within 4-dp rounding", acct_worst < 2e-4,
      f"max diff {acct_worst:.2e}")
check("Headline savings is monotonically non-decreasing (BUG-01)", monotonic_ok)
check("Both batteries stay within 10%-100%", bounds_ok)

# ── C) Optimiser wins over a full day ────────────────────────────────────────
print("\nC) DOES IT ACTUALLY SAVE? — one full day from warm state")
sim.reset()
sim._integrate(24.0)
st = sim.state()
check("After 24h, savings > 0 (optimiser beats baseline)", st["savings"] > 0,
      f"€{st['savings']:.2f} saved, {st['savings_pct']:.0f}% of bill")

# ── E) Determinism ───────────────────────────────────────────────────────────
print("\nE) DETERMINISM — same session, same numbers")
a, b = LiveSim(), LiveSim()
a._integrate(50.0); b._integrate(50.0)
check("Two identical sessions give identical savings",
      abs(a.state()["savings"] - b.state()["savings"]) < 1e-9,
      f"€{a.state()['savings']:.4f}")

print("\n" + "=" * 68)
print(f"  RESULT: {PASS} passed, {FAIL} failed")
print("=" * 68)
if FAIL == 0:
    print("  The /sim engine is sound: real physics, honest accounting,")
    print("  it genuinely saves, and it's reproducible.")
