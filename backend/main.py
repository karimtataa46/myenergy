"""
myEnergy API Server

Runs the control loop every 5 seconds and exposes REST endpoints
for the dashboard to consume.
"""

import asyncio
import os
import threading
from datetime import datetime, timezone
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pathlib import Path

import database
import weather as weather_module
import simulator as sim_module
import brain
import savings as savings_module
import live_sim as live_sim_module
from live_sim import live_sim
from brain import BrainInput

# ── Global state ─────────────────────────────────────────────────────────────

facility = sim_module.FacilitySimulator()
latest_snapshot: dict = {}
forecast_cache: list = []
_forecast_lock = threading.Lock()

TICK_INTERVAL_SECONDS = 5
FORECAST_REFRESH_MINUTES = 30

# ── Lifespan: start background tasks ─────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    database.init_db()
    await _refresh_forecast()
    asyncio.create_task(_control_loop())
    asyncio.create_task(_forecast_refresh_loop())
    yield


app = FastAPI(title="myEnergy API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

frontend_path = Path(__file__).parent.parent / "frontend"
app.mount("/static", StaticFiles(directory=str(frontend_path)), name="static")


# ── Background tasks ──────────────────────────────────────────────────────────

async def _control_loop():
    """Main energy control loop — runs every TICK_INTERVAL_SECONDS."""
    global latest_snapshot
    while True:
        try:
            with _forecast_lock:
                fc = forecast_cache[:]

            solar = facility.get_solar()
            battery = facility.get_battery()
            consumption = facility.get_consumption()
            upcoming = weather_module.get_upcoming_solar(fc, from_now_hours=2) if fc else 0.0

            tariff = 0.28 if 7 <= datetime.now(timezone.utc).hour < 22 else 0.12

            decision = brain.decide(BrainInput(
                solar=solar,
                battery=battery,
                consumption=consumption,
                upcoming_solar_kw=upcoming,
                current_tariff_eur_kwh=tariff,
            ))

            facility.apply_decision(decision.battery_kw, dt_seconds=TICK_INTERVAL_SECONDS)
            facility.accumulate_stats(solar.power_kw, decision.grid_kw, dt_seconds=TICK_INTERVAL_SECONDS)

            grid = facility.get_grid(decision.grid_kw)

            snap = {
                "ts": datetime.now(timezone.utc).isoformat(),
                "solar_kw": solar.power_kw,
                "battery_soc": facility.battery_soc,
                "battery_kw": decision.battery_kw,
                "grid_import_kw": grid.import_kw,
                "grid_export_kw": grid.export_kw,
                "consumption_kw": consumption.total_kw,
                "zones": consumption.zones,
                "action": decision.action.value,
                "reason": decision.reason,
                "co2_saved_kg": facility.co2_saved_kg,
                "cost_saved_eur": facility.cost_saved_eur,
                "solar_fraction": facility.solar_fraction,
                "upcoming_solar_kw": round(upcoming, 1),
                "tariff": tariff,
            }

            database.insert_snapshot(snap)
            # Report solar fraction over a stable trailing window (now that this
            # tick is persisted), not the since-restart counter that reads a
            # misleading 100% at startup. Fall back to the counter until there's
            # enough windowed data.
            windowed = database.solar_fraction_window(minutes=60)
            if windowed is not None:
                snap["solar_fraction"] = windowed
            latest_snapshot = snap

        except Exception as e:
            print(f"[control loop error] {e}")

        await asyncio.sleep(TICK_INTERVAL_SECONDS)


async def _forecast_refresh_loop():
    """Refresh weather forecast every 30 minutes."""
    while True:
        await asyncio.sleep(FORECAST_REFRESH_MINUTES * 60)
        await _refresh_forecast()


async def _refresh_forecast():
    global forecast_cache
    print("[weather] fetching forecast...")
    fc = await asyncio.to_thread(weather_module.fetch_forecast)
    with _forecast_lock:
        forecast_cache = fc
    print(f"[weather] got {len(fc)} hourly forecasts")


# ── API endpoints ─────────────────────────────────────────────────────────────

@app.get("/")
async def root():
    return FileResponse(str(frontend_path / "index.html"))


@app.get("/api/live")
async def get_live():
    """Current system state — called every second by dashboard."""
    return latest_snapshot


@app.get("/api/history")
async def get_history(minutes: int = 60):
    """Historical snapshots for charts."""
    return database.get_history_minutes(minutes)


@app.get("/api/forecast")
async def get_forecast():
    """Next 24 hours of solar forecast, starting from the current hour."""
    with _forecast_lock:
        fc = forecast_cache[:]
    # Only keep hours from the current hour onward — "incoming", not past.
    now_hour = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    upcoming = [f for f in fc if f.timestamp >= now_hour]
    return [
        {
            "ts": f.timestamp.isoformat(),
            "solar_kw": round(f.estimated_solar_kw, 1),
            "irradiance": round(f.solar_irradiance_wm2, 1),
            "clouds": f.cloud_cover_percent,
        }
        for f in upcoming[:24]
    ]


@app.get("/api/savings")
async def get_savings():
    """
    Month-to-date savings vs a dumb baseline controller, computed with the
    same validated simulation engine the analysis used.
    """
    return await asyncio.to_thread(savings_module.month_to_date)


# ── Live simulation session (per-second savings from the real engine) ────────

@app.get("/sim")
async def sim_page():
    return FileResponse(str(frontend_path / "sim.html"))


@app.get("/api/sim/live")
async def sim_live(session: Optional[str] = None):
    """Advance the caller's live session and return its current state."""
    return await asyncio.to_thread(live_sim_module.tick, session)


@app.post("/api/sim/reset")
async def sim_reset(session: Optional[str] = None):
    """Start a fresh live session for this caller."""
    await asyncio.to_thread(live_sim_module.reset, session)
    return {"ok": True}
