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
import estimate_service
import facility_live
import pricing_service
from live_sim import live_sim
from brain import BrainInput
from pydantic import BaseModel
from datetime import datetime, timezone, timedelta
from models import ShiftableDevice


class EstimateIn(BaseModel):
    city: str
    solar_kwp: float = 100.0
    battery_kwh: float = 200.0
    monthly_kwh: float = 46920.0
    # Optional exact place from the autocomplete pick (skip re-geocoding).
    lat: Optional[float] = None
    lon: Optional[float] = None
    country: Optional[str] = None
    country_code: Optional[str] = None


def _picked_place(inp: "EstimateIn"):
    if inp.lat is not None and inp.lon is not None and inp.country_code:
        return pricing_service.place_from(
            inp.city, inp.country or "", inp.country_code, inp.lat, inp.lon)
    return None


# Serve HTML with no-cache so browsers never show a stale old page.
_NOCACHE = {"Cache-Control": "no-cache, no-store, must-revalidate", "Pragma": "no-cache", "Expires": "0"}


def _page(name: str) -> FileResponse:
    return FileResponse(str(frontend_path / name), headers=_NOCACHE)

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

# 1. Define your devices somewhere outside the loop (or load them from a DB)
system_devices = [
    ShiftableDevice(
        id="ev_charger_1",
        name="Delivery Van EV",
        power_draw_kw=11.0,
        is_on=False,
        must_finish_by=datetime.now(timezone.utc) + timedelta(hours=12),  # Needs to be ready in 12 hours
        remaining_kwh_needed=40.0,  # Needs 40 kWh total
        is_interruptible=True
    ),
    ShiftableDevice(
        id="water_heater",
        name="Industrial Water Heater",
        power_draw_kw=15.0,
        is_on=False,
        must_finish_by=datetime.now(timezone.utc) + timedelta(hours=4),
        remaining_kwh_needed=10.0,
        is_interruptible=False  # Once started, don't stop until finished
    )
]


async def _control_loop():
    """Main energy control loop — runs every TICK_INTERVAL_SECONDS."""
    global latest_snapshot
    while True:
        try:
            with _forecast_lock:
                fc = forecast_cache[:]

            current_solar = weather_module.get_current_solar(fc)
            solar = facility.get_solar(override_kw=current_solar)
            battery = facility.get_battery()

            # Use your old total consumption as the "Base Load" (stuff we can't turn off)
            base_consumption = facility.get_consumption()
            upcoming = weather_module.get_upcoming_solar(fc, from_now_hours=2) if fc else 0.0
            tariff = 0.28 if 7 <= datetime.now(timezone.utc).hour < 22 else 0.12

            # 2. Feed the new inputs to the Brain
            decision = brain.decide(BrainInput(
                solar=solar,
                battery=battery,
                base_load_kw=base_consumption.total_kw,
                shiftable_devices=system_devices,
                upcoming_solar_kw=upcoming,
                current_tariff_eur_kwh=tariff,
            ))

            # 3. Apply device commands and tick down their required energy!
            for dev in system_devices:
                if not dev.is_fulfilled:
                    # Turn on or off based on the brain's command
                    dev.is_on = decision.device_commands.get(dev.id, False)

                    if dev.is_on:
                        # Calculate energy used during this 5-second tick
                        energy_used_kwh = dev.power_draw_kw * (TICK_INTERVAL_SECONDS / 3600.0)
                        dev.remaining_kwh_needed -= energy_used_kwh

                        # Prevent floating point dropping below exactly zero
                        if dev.remaining_kwh_needed <= 0:
                            dev.remaining_kwh_needed = 0
                            dev.is_on = False

            # 4. Apply the battery physics using the Brain's output
            facility.apply_decision(decision.battery_kw, dt_seconds=TICK_INTERVAL_SECONDS)
            facility.accumulate_stats(solar.power_kw, decision.grid_kw, dt_seconds=TICK_INTERVAL_SECONDS)

            grid = facility.get_grid(decision.grid_kw)

            # Reconcile the zone breakdown with the true total. consumption_kw is
            # base load + any shiftable device the brain switched on this tick, so
            # the zones must include those devices too — otherwise the bars sum to
            # the base load only and the shifted load is invisible on the dashboard.
            now = datetime.now(timezone.utc)
            zones = dict(base_consumption.zones)
            for dev in system_devices:
                if dev.is_on:
                    zones[dev.name] = round(dev.power_draw_kw, 2)

            # Compact per-device status so the UI can show WHAT is being shifted
            # and why (urgency capped so a past-deadline inf stays valid JSON).
            devices_status = [
                {
                    "name": dev.name,
                    "on": dev.is_on,
                    "remaining_kwh": round(dev.remaining_kwh_needed, 1),
                    "urgency": 0.0 if dev.is_fulfilled else round(min(dev.urgency(now), 99.9), 2),
                }
                for dev in system_devices
            ]

            # 5. Save the snapshot for the dashboard charts
            snap = {
                "ts": now.isoformat(),
                "solar_kw": solar.power_kw,
                "battery_soc": facility.battery_soc,
                "battery_kw": decision.battery_kw,
                "grid_import_kw": grid.import_kw,
                "grid_export_kw": grid.export_kw,
                "consumption_kw": decision.consumption_kw,  # base load + active shiftable
                "zones": zones,                             # now reconciles with consumption_kw
                "devices": devices_status,                  # flexible loads the brain controls
                "action": decision.action.value,
                "reason": decision.reason,
                "co2_saved_kg": facility.co2_saved_kg,
                "cost_saved_eur": facility.cost_saved_eur,
                "solar_fraction": facility.solar_fraction,
                "upcoming_solar_kw": round(upcoming, 1),
                "tariff": tariff,
            }

            database.insert_snapshot(snap)
            # Report solar fraction over a stable trailing window (survives restart),
            # not the since-restart counter that reads a misleading 100% at startup.
            windowed = database.solar_fraction_window(minutes=60)
            if windowed is not None:
                snap["solar_fraction"] = windowed
            latest_snapshot = snap          # <-- publish it for /api/live (was dropped)

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
    return _page("index.html")


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
    return _page("sim.html")


# ── Per-user estimate: user enters their facility, gets their own savings ────

@app.get("/estimate")
async def estimate_page():
    return _page("estimate.html")


@app.get("/api/cities")
async def api_cities(q: str = ""):
    """Autocomplete: cities matching the typed query (name + country + price flag)."""
    return await asyncio.to_thread(pricing_service.search_cities, q)


@app.post("/api/estimate")
async def api_estimate(inp: EstimateIn):
    """Run the validated engine on the user's own facility inputs."""
    return await asyncio.to_thread(
        estimate_service.estimate_savings,
        inp.city, inp.solar_kwp, inp.battery_kwh, inp.monthly_kwh, _picked_place(inp),
    )


# ── Live per-user facility dashboard (the /estimate → live view) ─────────────

@app.get("/facility")
async def facility_page():
    return _page("facility.html")


@app.post("/api/facility/start")
async def api_facility_start(inp: EstimateIn):
    """Spin up a live session for this facility; returns a session id."""
    sid = await asyncio.to_thread(
        facility_live.start, inp.city, inp.solar_kwp, inp.battery_kwh, inp.monthly_kwh,
        _picked_place(inp),
    )
    if sid is None:
        return {"error": f"Couldn't find “{inp.city}”. Try a nearby larger city."}
    return {"session": sid}


@app.get("/api/facility/live")
async def api_facility_live(session: str):
    """Live state for a facility session (polled every 2s by the dashboard)."""
    state = await asyncio.to_thread(facility_live.live, session)
    if state is None:
        return {"error": "session expired"}
    return state


@app.get("/api/sim/live")
async def sim_live(session: Optional[str] = None, speed: float = 1.0):
    """Advance the caller's live session and return its current state."""
    return await asyncio.to_thread(live_sim_module.tick, session, speed)


@app.post("/api/sim/reset")
async def sim_reset(session: Optional[str] = None):
    """Start a fresh live session for this caller."""
    await asyncio.to_thread(live_sim_module.reset, session)
    return {"ok": True}
