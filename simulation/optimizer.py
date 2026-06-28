"""
Optimal battery controller — Model Predictive Control (MPC) via Linear Programming.

This is what "predictive, full control, optimise as much as possible" actually
means in engineering terms. There are NO hand-written rules here. Every hour the
controller:

  1. Looks at the forecast for the next HORIZON hours (solar, load, prices).
  2. Solves for the single cheapest battery schedule over that whole window.
  3. Executes ONLY the first hour's action.
  4. Next hour, re-solves with fresh data (a "rolling horizon").

This is exactly how grid-scale batteries and real energy-management systems are
dispatched. The optimiser finds decisions no human rule-writer would think of.

The optimisation is a Linear Program:

  minimise   Σ_k  import[k]·price[k]  −  export[k]·feed_in[k]
                   −  leftover_soc · terminal_value     ← so it won't drain at the horizon end

  subject to, every hour k:
     balance :  solar[k] + import[k] + discharge[k] = load[k] + charge[k] + export[k]
     battery :  soc[k] = soc[k−1] + charge[k]·eff_c − discharge[k]/eff_d
     limits  :  0 ≤ charge ≤ max_charge,   0 ≤ discharge ≤ max_discharge
                soc_min ≤ soc ≤ soc_max,   import, export ≥ 0
"""

import numpy as np
from scipy.optimize import linprog

import factory as F
from engine import StepState


def optimal_battery_schedule(solar, load, price, feed_in, soc0,
                             terminal_value=None):
    """
    Solve the LP for one horizon. Returns the optimal per-hour plan, or None
    if the solver fails (caller should fall back to a safe action).
    """
    H = len(solar)
    cap = F.BATTERY_CAPACITY_KWH
    max_c, max_d = F.BATTERY_MAX_CHARGE_KW, F.BATTERY_MAX_DISCHARGE_KW
    eff_c, eff_d = F.CHARGE_EFFICIENCY, F.DISCHARGE_EFFICIENCY
    soc_min, soc_max = F.BATTERY_MIN_SOC * cap, F.BATTERY_MAX_SOC * cap
    if terminal_value is None:
        # Value of energy left in the battery at the horizon's end. With a long
        # enough rolling horizon (36h) end-effects are negligible and 0 matches
        # the true global optimum (verified in debug_lp.py). For a 24/7
        # deployment you'd set this to the expected forward marginal value.
        terminal_value = 0.0

    # Variable vector x = [ charge(H) | discharge(H) | import(H) | export(H) | soc(H) ]
    oC, oD, oGI, oGE, oS = 0, H, 2 * H, 3 * H, 4 * H
    N = 5 * H

    # ── Objective ────────────────────────────────────────────────────────────
    c = np.zeros(N)
    for k in range(H):
        c[oGI + k] = price[k]        # pay for imports
        c[oGE + k] = -feed_in[k]     # earn from exports
    c[oS + (H - 1)] = -terminal_value  # reward energy left in the battery at the end

    # ── Equality constraints A_eq · x = b_eq ─────────────────────────────────
    A_eq = np.zeros((2 * H, N))
    b_eq = np.zeros(2 * H)

    for k in range(H):
        # Energy balance:  import − export + discharge − charge = load − solar
        A_eq[k, oGI + k] = 1.0
        A_eq[k, oGE + k] = -1.0
        A_eq[k, oD + k] = 1.0
        A_eq[k, oC + k] = -1.0
        b_eq[k] = load[k] - solar[k]

        # Battery dynamics: soc[k] − soc[k−1] − eff_c·charge[k] + discharge[k]/eff_d = (soc0 if k==0 else 0)
        r = H + k
        A_eq[r, oS + k] = 1.0
        if k > 0:
            A_eq[r, oS + (k - 1)] = -1.0
        A_eq[r, oC + k] = -eff_c
        A_eq[r, oD + k] = 1.0 / eff_d
        b_eq[r] = soc0 if k == 0 else 0.0

    # ── Bounds ───────────────────────────────────────────────────────────────
    grid_max = F.GRID_MAX_KW
    bounds = (
        [(0, max_c)] * H +          # charge
        [(0, max_d)] * H +          # discharge
        [(0, grid_max)] * H +       # import  (bounded by grid connection)
        [(0, grid_max)] * H +       # export  (bounded by grid connection)
        [(soc_min, soc_max)] * H    # soc
    )

    res = linprog(c, A_eq=A_eq, b_eq=b_eq, bounds=bounds, method="highs")
    if not res.success:
        return None

    x = res.x
    return {
        "charge": x[oC:oC + H],
        "discharge": x[oD:oD + H],
        "import": x[oGI:oGI + H],
        "export": x[oGE:oGE + H],
        "soc": x[oS:oS + H],
        "cost": res.fun,
    }


def optimal(state: StepState) -> float:
    """
    Engine-compatible controller. Plans over the forecast horizon and returns
    the first hour's battery action (+charge / −discharge at the AC bus).
    """
    solar = state.forecast_solar_kwh
    load = state.forecast_load_kwh
    H = len(solar)
    if H == 0:
        return 0.0

    # Tariff for each future hour comes from its hour-of-day.
    price = [F.tariff((state.hour + k) % 24) for k in range(H)]
    feed_in = [F.FEED_IN_TARIFF] * H

    sched = optimal_battery_schedule(solar, load, price, feed_in, state.soc_kwh)
    if sched is None:
        # Safe fallback if the solver hiccups: behave reactively.
        return state.solar_kwh - state.load_kwh

    return float(sched["charge"][0] - sched["discharge"][0])
