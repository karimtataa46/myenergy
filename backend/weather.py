"""
Fetches real solar irradiance forecasts from Open-Meteo (free, no API key).
Falls back to synthetic data if offline.
"""

import math
import os
import sys
from datetime import datetime, timedelta, timezone
from typing import Optional
import urllib.request
import json

from models import WeatherForecastHour

# Single source of truth for the array size lives in the validated factory.
_SIM_DIR = os.path.join(os.path.dirname(__file__), "..", "simulation")
if os.path.abspath(_SIM_DIR) not in sys.path:
    sys.path.insert(0, os.path.abspath(_SIM_DIR))
import factory as F   # noqa: E402

# Default: Brussels (change to your facility's coordinates)
DEFAULT_LAT = 50.85
DEFAULT_LON = 4.35

# Facility panel config — installed capacity comes from the factory profile so
# live data, forecast, and the savings model all assume ONE array size.
PANEL_CAPACITY_KW = F.SOLAR_NAMEPLATE_KW   # total installed solar capacity (kWp)
PANEL_EFFICIENCY = 0.18          # 18% panel efficiency
PANEL_AREA_M2 = 556              # 100kW / (18% * 1000 W/m2) ≈ 556 m2


def irradiance_to_solar_kw(irradiance_wm2: float) -> float:
    """Convert solar irradiance (W/m²) to estimated facility output (kW)."""
    raw_kw = (irradiance_wm2 * PANEL_AREA_M2 * PANEL_EFFICIENCY) / 1000
    return min(raw_kw, PANEL_CAPACITY_KW)  # cap at installed capacity


def fetch_forecast(lat: float = DEFAULT_LAT, lon: float = DEFAULT_LON) -> list[WeatherForecastHour]:
    """
    Fetch 48-hour solar irradiance forecast from Open-Meteo.
    Returns list of WeatherForecastHour sorted by timestamp.
    """
    url = (
        f"https://api.open-meteo.com/v1/forecast"
        f"?latitude={lat}&longitude={lon}"
        f"&hourly=shortwave_radiation,cloudcover,temperature_2m"
        f"&forecast_days=2"
        f"&timezone=UTC"   # return real UTC times so they match datetime.now(timezone.utc)
    )

    try:
        with urllib.request.urlopen(url, timeout=5) as response:
            data = json.loads(response.read())
        return _parse_open_meteo(data)
    except Exception:
        # Offline fallback: generate synthetic clear-sky irradiance
        return _synthetic_forecast()


def _parse_open_meteo(data: dict) -> list[WeatherForecastHour]:
    hourly = data["hourly"]
    times = hourly["time"]
    irradiances = hourly["shortwave_radiation"]
    clouds = hourly["cloudcover"]
    temps = hourly["temperature_2m"]

    result = []
    for i, t in enumerate(times):
        dt = datetime.fromisoformat(t).replace(tzinfo=timezone.utc)
        irr = float(irradiances[i] or 0)
        result.append(WeatherForecastHour(
            timestamp=dt,
            solar_irradiance_wm2=irr,
            cloud_cover_percent=float(clouds[i] or 0),
            temperature_c=float(temps[i] or 20),
            estimated_solar_kw=irradiance_to_solar_kw(irr),
        ))
    return result


def _synthetic_forecast() -> list[WeatherForecastHour]:
    """Clear-sky sinusoidal model as offline fallback."""
    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    result = []
    for h in range(48):
        dt = now + timedelta(hours=h)
        hour_of_day = dt.hour
        # Solar peaks at noon (hour 12), zero before sunrise (6) and after sunset (20)
        if 6 <= hour_of_day <= 20:
            angle = math.pi * (hour_of_day - 6) / 14
            irr = 800 * math.sin(angle)
        else:
            irr = 0.0
        result.append(WeatherForecastHour(
            timestamp=dt,
            solar_irradiance_wm2=irr,
            cloud_cover_percent=10.0,
            temperature_c=20.0,
            estimated_solar_kw=irradiance_to_solar_kw(irr),
        ))
    return result


def get_upcoming_solar(
    forecast: list[WeatherForecastHour],
    from_now_hours: int = 3,
) -> float:
    """Returns average expected solar output over the next N hours (kW)."""
    now = datetime.now(timezone.utc)
    cutoff = now + timedelta(hours=from_now_hours)
    upcoming = [f for f in forecast if now <= f.timestamp <= cutoff]
    if not upcoming:
        return 0.0
    return sum(f.estimated_solar_kw for f in upcoming) / len(upcoming)
