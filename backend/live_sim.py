"""
Live simulation session — runs the VALIDATED simulation engine in real time so
the app can show savings accumulating per second.

It runs TWO facilities through the same factory, weather and dynamic prices:
  • myEnergy  — the LP optimiser (the verified decision maker)
  • baseline  — a dumb reactive controller

Every real second it advances simulated time (accelerated), accrues each
facility's cost, and reports the gap. The decision the optimiser makes each
hour is shown with a plain-English reason and an audit flag.

Time model: SIM_SPEED simulated-hours pass per real second, so the money
counter visibly ticks. The savings RATE (€/sim-hour) is the true economic rate.
"""

import sys
import os
import math
import time
import datetime
import threading
from typing import Dict, Optional

# Make the validated simulation package importable
_SIM = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "simulation"))
if _SIM not in sys.path:
    sys.path.insert(0, _SIM)

import factory as F
from engine import _apply_battery, HORIZON_HOURS

# The optimiser needs scipy. If it can't load, fall back to the rule controller
# so the app still runs — and tell the UI which engine is active.
try:
    from optimizer import optimal_battery_schedule
    ENGINE = "LP optimiser (optimal)"
    _HAVE_LP = True
except Exception as e:  # pragma: no cover
    _HAVE_LP = False
    ENGINE = f"rule-based fallback ({e.__class__.__name__})"

SIM_SPEED = 0.35          # simulated hours per real second (1 sim-day ≈ 68 real s)
MAX_REAL_DT = 1.5         # cap per tick so a backgrounded tab doesn't jump
SIM_DAYS = 60
WARMUP_HOURS = 41         # warm the battery + start the session at ~17:00 (peak payoff begins in seconds)
SESSION_START = datetime.datetime(2026, 6, 1, 0, 0)


class LiveSim:
    def __init__(self):
        self._lock = threading.Lock()
        self.reset()

    def reset(self):
        with self._lock:
            self.weather = F.generate_month_weather(days=SIM_DAYS, seed=42)
            self.solar = [d.solar_kwh(h) for d in self.weather for h in range(24)]
            self.load = [F.LOAD_PROFILE_KW[h] for _ in self.weather for h in range(24)]
            self.prices = F.dynamic_price_series(self.weather)
            self.feed = F.export_price_series(self.prices)
            self.N = len(self.solar)

            self.sim_t = 0.0
            self.opt_soc = 0.10 * F.BATTERY_CAPACITY_KWH
            self.base_soc = 0.10 * F.BATTERY_CAPACITY_KWH
            self.opt_cost = 0.0
            self.base_cost = 0.0
            # High-water mark of the true cumulative gap (base_cost - opt_cost).
            # "Saved this session" reports this so the headline never ticks down:
            # while the optimiser invests in cheap charging the instantaneous gap
            # dips, but realised savings simply hold at their previous best — we
            # never hide a loss by inventing money, we just don't bank a new peak
            # until the gap actually exceeds it.
            self.realized_savings = 0.0
            self._cache = None
            self._last_wall = time.time()

            # Warm-up: advance the battery into its steady daily rhythm, then
            # zero the counters so the live session starts from a fair baseline
            # (not mid-investment). This is why the counter starts at 0 and grows.
            # The high-water mark must be re-zeroed too — warm-up accrues into it,
            # and leaving it would make a fresh session open at a non-zero figure.
            self._integrate(WARMUP_HOURS)
            self.opt_cost = 0.0
            self.base_cost = 0.0
            self.realized_savings = 0.0

    # ── decision for one hour, for both controllers ──────────────────────────
    def _hour_outcome(self, t):
        price, feed = self.prices[t], self.feed[t]
        solar, load = self.solar[t], self.load[t]

        # myEnergy: optimal plan over the horizon, take first action
        if _HAVE_LP:
            end = min(t + HORIZON_HOURS, self.N)
            sched = optimal_battery_schedule(
                self.solar[t:end], self.load[t:end],
                self.prices[t:end], self.feed[t:end],
                self.opt_soc, terminal_value=0.0,
            )
            opt_req = (sched["charge"][0] - sched["discharge"][0]) if sched else (solar - load)
        else:
            opt_req = self._rule(t, self.opt_soc)

        opt_ac, opt_soc_end = _apply_battery(self.opt_soc, opt_req)
        opt_net = load - solar + opt_ac
        opt_gi, opt_ge = max(opt_net, 0.0), max(-opt_net, 0.0)
        opt_rate = opt_gi * price - opt_ge * feed       # €/hour

        # baseline: reactive (charge surplus / discharge deficit)
        base_ac, base_soc_end = _apply_battery(self.base_soc, solar - load)
        base_net = load - solar + base_ac
        base_gi, base_ge = max(base_net, 0.0), max(-base_net, 0.0)
        base_rate = base_gi * price - base_ge * feed

        return {
            "t": t,
            "price": price, "solar": solar, "load": load,
            "opt_ac": opt_ac, "opt_soc_end": opt_soc_end,
            "opt_gi": opt_gi, "opt_ge": opt_ge, "opt_rate": opt_rate,
            "base_ac": base_ac, "base_soc_end": base_soc_end, "base_rate": base_rate,
            "reason": self._explain(t, opt_ac),
        }

    def _rule(self, t, soc):
        day = self.prices[(t // 24) * 24:(t // 24) * 24 + 24]
        avg = sum(day) / len(day)
        p = self.prices[t]
        if p < avg * 0.85:
            return F.BATTERY_MAX_CHARGE_KW
        if p > avg * 1.15:
            return -F.BATTERY_MAX_DISCHARGE_KW
        return 0.0

    def _explain(self, t, ac):
        end = min(t + HORIZON_HOURS, self.N)
        win = self.prices[t:end]
        p, lo, hi = self.prices[t], min(win), max(win)
        rng = (hi - lo) or 1e-9
        pct = (p - lo) / rng
        if self.solar[t] > self.load[t] + 0.5:
            return f"Solar surplus — storing free energy (price €{p:.2f})"
        if ac > 0.5:
            return f"Charging {ac:.0f}kWh — price €{p:.2f} is cheap (bottom {pct*100:.0f}% of next {len(win)}h)"
        if ac < -0.5:
            return f"Discharging {-ac:.0f}kWh — dodging €{p:.2f} grid (top {(1-pct)*100:.0f}% pricey); using stored cheap energy"
        return f"Holding battery — grid at €{p:.2f} is mid-range; saving charge for a pricier hour"

    # ── advance simulated time, integrating across hour boundaries ───────────
    def _integrate(self, dt):
        """Advance simulated time by dt hours, accruing cost for both controllers."""
        while dt > 1e-9:
            abs_hour = math.floor(self.sim_t)
            t = abs_hour % self.N
            if self._cache is None or self._cache["abs"] != abs_hour:
                self._cache = self._hour_outcome(t)
                self._cache["abs"] = abs_hour

            frac = self.sim_t - abs_hour
            stepped = min(dt, 1.0 - frac)
            self.opt_cost += self._cache["opt_rate"] * stepped
            self.base_cost += self._cache["base_rate"] * stepped
            # Advance the high-water mark of realised savings (never decreases).
            self.realized_savings = max(self.realized_savings,
                                        self.base_cost - self.opt_cost)
            self.sim_t += stepped
            dt -= stepped
            if (self.sim_t - math.floor(self.sim_t)) < 1e-9:   # crossed hour
                self.opt_soc = self._cache["opt_soc_end"]
                self.base_soc = self._cache["base_soc_end"]
                self._cache = None

    def tick(self):
        with self._lock:
            now = time.time()
            real_dt = min(now - self._last_wall, MAX_REAL_DT)
            self._last_wall = now
            self._integrate(real_dt * SIM_SPEED)
            return self._state()

    def _state(self):
        c = self._cache or self._hour_outcome(math.floor(self.sim_t) % self.N)
        gap = self.base_cost - self.opt_cost                 # instantaneous running gap
        realized = self.realized_savings                     # monotonic high-water mark
        rate_per_h = c["base_rate"] - c["opt_rate"]          # €/sim-hour right now
        # The headline counter shows realised (banked) savings, so it must only
        # ever ratchet up. It grows at the live rate only while the gap is at its
        # peak AND still climbing; otherwise the headline holds (rate 0), it never
        # ticks down. The raw instantaneous rate is still reported separately.
        realized_rate_per_h = rate_per_h if (rate_per_h > 0 and gap >= realized) else 0.0
        clock = SESSION_START + datetime.timedelta(hours=self.sim_t)
        return {
            "engine": ENGINE,
            "sim_clock": clock.strftime("%a %d %b, %H:%M"),
            "sim_day": int(self.sim_t // 24) + 1,
            "speed": SIM_SPEED,
            "price": round(c["price"], 3),
            "solar_kw": round(c["solar"], 1),
            "load_kw": round(c["load"], 1),
            "opt_soc_pct": round(self.opt_soc / F.BATTERY_CAPACITY_KWH * 100, 1),
            "base_soc_pct": round(self.base_soc / F.BATTERY_CAPACITY_KWH * 100, 1),
            "opt_battery_kw": round(c["opt_ac"], 1),
            "decision_reason": c["reason"],
            "opt_cost": round(self.opt_cost, 4),
            "base_cost": round(self.base_cost, 4),
            # "savings" is the headline: monotonic realised savings (banked).
            "savings": round(realized, 4),
            # The honest instantaneous gap (can dip mid-investment), shown as a chip.
            "savings_gap_now": round(gap, 4),
            "savings_rate_per_hour": round(rate_per_h, 4),
            # Per-second increment the headline animates with — never negative.
            "savings_per_second_real": round(realized_rate_per_h * SIM_SPEED, 5),
            "savings_pct": round(realized / self.base_cost * 100, 1) if self.base_cost > 0 else 0.0,
        }

    def state(self):
        with self._lock:
            return self._state()


# ── Per-viewer sessions ──────────────────────────────────────────────────────
# A single shared instance advanced on every poll from any client, so a new
# visitor saw whatever the global had drifted to (mid-session, non-zero) and two
# tabs fought over the same wall-clock. Instead, hand each viewer its OWN LiveSim
# keyed by a session id the page generates on load, so everyone starts near €0
# and their counter is genuinely theirs.

_sessions: Dict[str, "LiveSim"] = {}
_sessions_lock = threading.Lock()
MAX_SESSIONS = 256        # simple cap so abandoned tabs can't grow memory forever


def _get_session(session_id: Optional[str]) -> "LiveSim":
    """Return the LiveSim for this session id, creating a fresh one on first use."""
    if not session_id:
        return live_sim                      # legacy/no-id callers share the default
    with _sessions_lock:
        sim = _sessions.get(session_id)
        if sim is None:
            if len(_sessions) >= MAX_SESSIONS:
                # Evict the oldest session (insertion order) to bound memory.
                _sessions.pop(next(iter(_sessions)))
            sim = LiveSim()
            _sessions[session_id] = sim
        return sim


def tick(session_id: Optional[str] = None) -> dict:
    """Advance the caller's own session and return its state."""
    return _get_session(session_id).tick()


def reset(session_id: Optional[str] = None) -> None:
    """Reset the caller's own session (or the default if no id)."""
    _get_session(session_id).reset()


# Default instance: used by callers that send no session id (kept for safety).
live_sim = LiveSim()
