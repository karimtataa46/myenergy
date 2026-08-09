"""
Live per-facility dashboard — a per-session simulation of the USER's facility.

After a user calculates their facility on /estimate, we spin up a FacilityLive
for their inputs and stream its live state (solar / battery / grid / decision)
to the same WHOOP dashboard, polled every 2s — just like the demo, but on THEIR
numbers, THEIR city's real weather, and THEIR electricity price. The battery SOC
is carried across polls so it drifts in real time like a real site.
"""

import sys
import os
import random
import time
import threading
import uuid
from datetime import datetime, timezone

_SIM = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "simulation"))
if _SIM not in sys.path:
    sys.path.insert(0, _SIM)

import factory as F                       # noqa: E402
from engine import StepState, HORIZON_HOURS, _apply_battery  # noqa: E402
import weather as weather_module          # noqa: E402
import estimate_service                   # noqa: E402

try:
    from optimizer import optimal         # noqa: E402
    _DECIDE = optimal
except Exception:
    from controllers import predictive as _DECIDE  # fallback if scipy missing

# Fraction of total load per zone (for the consumption breakdown).
ZONE_SHARES = {
    "production_line_a": 0.37, "production_line_b": 0.30,
    "hvac": 0.16, "lighting": 0.10, "office": 0.07,
}


class FacilityLive:
    def __init__(self, cfg, place, projected):
        self.cfg = cfg
        self.place = place
        self.projected = projected
        self.forecast = weather_module.fetch_forecast(place.latitude, place.longitude)
        self._plan_cache = None                       # (hour, plan) — recomputed hourly
        self._lock = threading.Lock()

    # ── real weather solar for THIS array, right now ─────────────────────────
    def _current_solar_kw(self):
        ref = weather_module.get_current_solar(self.forecast) or 0.0   # for a 100 kWp ref
        return max(0.0, ref * (self.cfg.solar_nameplate_kw / F.SOLAR_NAMEPLATE_KW))

    def _solar_by_dayhour(self):
        """{hours since today 00:00 UTC -> solar kW scaled to this array} from real forecast."""
        cfg = self.cfg
        now = datetime.now(timezone.utc)
        day0 = now.replace(hour=0, minute=0, second=0, microsecond=0)
        scale = cfg.solar_nameplate_kw / F.SOLAR_NAMEPLATE_KW
        m = {}
        for f in self.forecast:
            dh = int((f.timestamp - day0).total_seconds() // 3600)
            if 0 <= dh < 72:
                m[dh] = max(0.0, f.estimated_solar_kw * scale)
        return m

    def _plan_to_now(self):
        """
        Deterministically compute the battery SOC + this-hour decision for the
        CURRENT time by running the optimiser over today's REAL weather, with a
        one-day warm-up so the arbitrary start value doesn't matter. This is why
        the battery now reflects the actual time of day (e.g. what it did
        overnight) instead of a frozen number. Cached per hour.
        Returns (soc_start_of_hour, soc_end_of_hour, battery_kw, hour, next_solar).
        """
        cfg = self.cfg
        hour_now = datetime.now(timezone.utc).hour
        if self._plan_cache is not None and self._plan_cache[0] == hour_now:
            return self._plan_cache[1]

        solar_map = self._solar_by_dayhour()
        solar_at = lambda dh: solar_map.get(dh, 0.0)
        load_at = lambda dh: cfg.load_profile_kw[dh % 24]

        def step_hour(dh, soc):
            win_solar = [solar_at(dh + k) for k in range(HORIZON_HOURS)]
            win_load = [load_at(dh + k) for k in range(HORIZON_HOURS)]
            st = StepState(
                hour=dh % 24, solar_kwh=solar_at(dh), load_kwh=load_at(dh), soc_kwh=soc,
                capacity_kwh=cfg.battery_capacity_kwh,
                forecast_next_solar_kwh=(sum(win_solar[1:4]) / 3 if len(win_solar) > 3 else 0.0),
                forecast_tomorrow_deficit_kwh=0.0,
                forecast_solar_kwh=win_solar, forecast_load_kwh=win_load, cfg=cfg,
            )
            return _apply_battery(soc, _DECIDE(st), cfg)   # (battery_kw, new_soc)

        soc = 0.50 * cfg.battery_capacity_kwh
        for h in range(24):                     # warm-up day -> steady state
            _, soc = step_hour(h, soc)
        soc_start, battery_kw = soc, 0.0
        for h in range(hour_now + 1):           # today up to the current hour
            soc_start = soc
            battery_kw, soc = step_hour(h, soc)

        result = (soc_start, soc, battery_kw, hour_now, solar_at(hour_now + 1))
        self._plan_cache = (hour_now, result)
        return result

    def _explain(self, battery_kw, solar, load, price):
        if solar > load + 0.5:
            return "Solar surplus — storing free energy", "battery_charge_from_solar"
        if battery_kw > 0.5:
            return f"Charging {battery_kw:.0f} kW at €{price:.2f}", "battery_charge_from_grid"
        if battery_kw < -0.5:
            return f"Discharging {-battery_kw:.0f} kW to dodge €{price:.2f} grid", "battery_discharge"
        return f"Grid covering load at €{price:.2f}/kWh", "grid_import"

    def state(self):
        with self._lock:
            soc_start, soc_end, battery_kw, hour, next_solar = self._plan_to_now()
            now = datetime.now(timezone.utc)
            frac = now.minute / 60.0
            soc = soc_start + (soc_end - soc_start) * frac      # smooth within the hour
            cfg = self.cfg

            solar = self._current_solar_kw()                     # real current solar
            load = cfg.load_profile_kw[hour] * random.uniform(0.97, 1.03)
            grid_net = load - solar + battery_kw
            grid_import = max(grid_net, 0.0)
            grid_export = max(-grid_net, 0.0)
            self_pow = 100.0 * (1 - grid_import / load) if load > 0 else 100.0
            self_pow = max(0.0, min(100.0, self_pow))
            reason, action = self._explain(battery_kw, solar, load, cfg.tariff(hour))

            return {
                "ts": now.isoformat(),
                "facility": self.place.name, "country": self.place.country,
                "priced": self.projected.get("priced", True),
                "solar_kw": round(solar, 2),
                "battery_soc": round(soc / cfg.battery_capacity_kwh * 100, 1),
                "battery_kw": round(battery_kw, 2),
                "grid_import_kw": round(grid_import, 2),
                "grid_export_kw": round(grid_export, 2),
                "consumption_kw": round(load, 2),
                "tariff": round(cfg.tariff(hour), 3),
                "upcoming_solar_kw": round(next_solar, 1),
                "self_powered_pct": round(self_pow, 1),
                "solar_peak_kw": round(cfg.solar_peak_kw, 1),
                "action": action, "reason": reason,
                "zones": {z: round(load * fr, 2) for z, fr in ZONE_SHARES.items()},
                "solar_kwp": round(cfg.solar_nameplate_kw),
                "battery_kwh": round(cfg.battery_capacity_kwh),
                "projected_monthly_eur": self.projected.get("saved_eur", 0),
                "projected_annual_eur": self.projected.get("annual_eur", 0),
                "projected_pct": self.projected.get("saved_pct", 0),
                "co2_month_kg": self.projected.get("co2_avoided_kg", 0),
            }


# ── per-viewer session registry ──────────────────────────────────────────────
_sessions = {}
_reg_lock = threading.Lock()
MAX_SESSIONS = 256


def start(city, solar_kwp, battery_kwh, monthly_kwh, place=None):
    """Create a live session for these inputs. Returns session id, or None."""
    cfg, place, _ = estimate_service.build_facility(
        city, solar_kwp, battery_kwh, monthly_kwh, place=place)
    if cfg is None:
        return None
    projected = estimate_service.estimate_savings(
        city, solar_kwp, battery_kwh, monthly_kwh, place=place)
    sid = uuid.uuid4().hex
    with _reg_lock:
        if len(_sessions) >= MAX_SESSIONS:
            _sessions.pop(next(iter(_sessions)))
        _sessions[sid] = FacilityLive(cfg, place, projected)
    return sid


def live(sid):
    with _reg_lock:
        fl = _sessions.get(sid)
    return fl.state() if fl else None
