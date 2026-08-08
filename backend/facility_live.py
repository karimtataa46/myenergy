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
from engine import StepState, HORIZON_HOURS  # noqa: E402
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
        self.soc = 0.60 * cfg.battery_capacity_kwh    # start at 60%
        self.last = time.time()
        self._lock = threading.Lock()

    # ── real weather solar for THIS array, right now ─────────────────────────
    def _current_solar_kw(self):
        ref = weather_module.get_current_solar(self.forecast) or 0.0   # for a 100 kWp ref
        return max(0.0, ref * (self.cfg.solar_nameplate_kw / F.SOLAR_NAMEPLATE_KW))

    def _forecast_window(self, hour):
        """Next HORIZON hours of (solar, load) for the optimiser — real forecast."""
        cfg = self.cfg
        now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
        upcoming = [f for f in self.forecast if f.timestamp >= now][:HORIZON_HOURS]
        scale = cfg.solar_nameplate_kw / F.SOLAR_NAMEPLATE_KW
        win_solar = [max(0.0, f.estimated_solar_kw * scale) for f in upcoming]
        if not win_solar:
            win_solar = [self._current_solar_kw()]
        win_load = [cfg.load_profile_kw[(hour + k) % 24] for k in range(len(win_solar))]
        return win_solar, win_load

    def _apply_live(self, req_kw, dt_h):
        """Clamp the desired battery power to rate + SOC, advance SOC over dt_h."""
        cfg = self.cfg
        min_kwh = cfg.battery_min_soc * cfg.battery_capacity_kwh
        max_kwh = cfg.battery_max_soc * cfg.battery_capacity_kwh
        if req_kw >= 0:                                   # charge
            kw = min(req_kw, cfg.battery_max_charge_kw)
            stored = kw * cfg.charge_efficiency * dt_h
            room = max_kwh - self.soc
            if stored > room:
                stored = max(room, 0.0)
                kw = (stored / dt_h / cfg.charge_efficiency) if dt_h > 0 else 0.0
            self.soc += stored
            return kw
        else:                                             # discharge
            kw = max(req_kw, -cfg.battery_max_discharge_kw)
            drawn = (-kw) / cfg.discharge_efficiency * dt_h
            avail = self.soc - min_kwh
            if drawn > avail:
                drawn = max(avail, 0.0)
                kw = -((drawn / dt_h) * cfg.discharge_efficiency) if dt_h > 0 else 0.0
            self.soc -= drawn
            return kw

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
            now = time.time()
            dt_h = min((now - self.last) / 3600.0, 1.0 / 60.0)   # cap at 1 min
            self.last = now
            dtn = datetime.now(timezone.utc)
            hour = dtn.hour
            cfg = self.cfg

            solar = self._current_solar_kw()
            load = cfg.load_profile_kw[hour] * random.uniform(0.96, 1.04)

            win_solar, win_load = self._forecast_window(hour)
            fc_next = sum(win_solar[1:4]) / 3 if len(win_solar) > 3 else solar
            state = StepState(
                hour=hour, solar_kwh=solar, load_kwh=load, soc_kwh=self.soc,
                capacity_kwh=cfg.battery_capacity_kwh,
                forecast_next_solar_kwh=fc_next, forecast_tomorrow_deficit_kwh=0.0,
                forecast_solar_kwh=win_solar, forecast_load_kwh=win_load, cfg=cfg,
            )
            req = _DECIDE(state)
            battery_kw = self._apply_live(req, dt_h)

            grid_net = load - solar + battery_kw
            grid_import = max(grid_net, 0.0)
            grid_export = max(-grid_net, 0.0)
            self_pow = 100.0 * (1 - grid_import / load) if load > 0 else 100.0
            self_pow = max(0.0, min(100.0, self_pow))
            reason, action = self._explain(battery_kw, solar, load, cfg.tariff(hour))

            return {
                "ts": dtn.isoformat(),
                "facility": self.place.name, "country": self.place.country,
                "priced": self.projected.get("priced", True),
                "solar_kw": round(solar, 2),
                "battery_soc": round(self.soc / cfg.battery_capacity_kwh * 100, 1),
                "battery_kw": round(battery_kw, 2),
                "grid_import_kw": round(grid_import, 2),
                "grid_export_kw": round(grid_export, 2),
                "consumption_kw": round(load, 2),
                "tariff": round(cfg.tariff(hour), 3),
                "upcoming_solar_kw": round(fc_next, 1),
                "self_powered_pct": round(self_pow, 1),
                "solar_peak_kw": round(cfg.solar_peak_kw, 1),
                "action": action, "reason": reason,
                "zones": {z: round(load * frac, 2) for z, frac in ZONE_SHARES.items()},
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
