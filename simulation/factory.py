"""
Mid-sized manufacturing factory profile.

All the physical facts about the site live here so every test uses the
SAME assumptions. Change a number here, every test updates.
"""

import math
import random
from dataclasses import dataclass, field
from typing import List


# ── Electricity tariff (Belgium-style commercial, EUR/kWh) ───────────────────
PEAK_TARIFF = 0.28        # 07:00–22:00
OFFPEAK_TARIFF = 0.12     # 22:00–07:00
FEED_IN_TARIFF = 0.05     # what the grid pays you for export (low, realistic 2026)

PEAK_START = 7
PEAK_END = 22             # peak is [7, 22)

# Grid connection capacity (kW). Every facility has a contracted maximum it can
# import/export. Also bounds the optimiser so it can't exploit unphysical flows.
GRID_MAX_KW = 250.0

# ── Grid carbon intensity (kg CO2 per kWh) ───────────────────────────────────
# Night grid is cleaner in the EU (more nuclear/wind, fewer gas peakers).
CO2_PEAK = 0.210
CO2_OFFPEAK = 0.120

# ── Battery ──────────────────────────────────────────────────────────────────
BATTERY_CAPACITY_KWH = 200.0
BATTERY_MAX_CHARGE_KW = 50.0
BATTERY_MAX_DISCHARGE_KW = 50.0
BATTERY_MIN_SOC = 0.10         # never discharge below 10% (protect battery)
BATTERY_MAX_SOC = 1.00
CHARGE_EFFICIENCY = 0.95       # AC -> stored
DISCHARGE_EFFICIENCY = 0.95    # stored -> AC  (round trip ~0.90)

# ── Solar array ──────────────────────────────────────────────────────────────
# Single source of truth for the facility's PV array. Two distinct quantities:
#   SOLAR_NAMEPLATE_KW — installed DC capacity (the inverter/grid cap)
#   SOLAR_PEAK_KW      — realistic clear-sky AC peak the array actually hits at noon
SOLAR_NAMEPLATE_KW = 100.0     # installed capacity (kWp)
SOLAR_PEAK_KW = 62.0           # realistic clear-sky peak for a 100 kWp array
SUNRISE_HOUR = 6
SUNSET_HOUR = 20


# ── Factory load: hourly demand in kW (two-shift manufacturing) ──────────────
# index = hour of day 0..23
LOAD_PROFILE_KW: List[float] = [
    30, 30, 30, 30, 30, 32,    # 00–05  night idle (security, HVAC, standby)
    45, 70,                    # 06–07  morning ramp-up
    95, 100, 100, 100,         # 08–11  day shift full
    85,                        # 12     lunch dip
    100, 100, 100, 100, 100,   # 13–17  day shift full
    75, 60,                    # 18–19  evening wind-down
    45, 40,                    # 20–21
    35, 32,                    # 22–23  night
]


def is_peak(hour: int) -> bool:
    return PEAK_START <= hour < PEAK_END


def tariff(hour: int) -> float:
    return PEAK_TARIFF if is_peak(hour) else OFFPEAK_TARIFF


def grid_co2(hour: int) -> float:
    return CO2_PEAK if is_peak(hour) else CO2_OFFPEAK


def clear_sky_kw(hour: int) -> float:
    """Solar output (kW) on a perfectly clear day at this hour."""
    if SUNRISE_HOUR <= hour <= SUNSET_HOUR:
        angle = math.pi * (hour - SUNRISE_HOUR) / (SUNSET_HOUR - SUNRISE_HOUR)
        return SOLAR_PEAK_KW * math.sin(angle)
    return 0.0


@dataclass
class DayWeather:
    """One day's worth of weather. cloud_factor 0=clear, 1=fully overcast."""
    cloud_factor: float

    def solar_kwh(self, hour: int) -> float:
        # kWh produced during this 1-hour slot
        return clear_sky_kw(hour) * (1.0 - 0.85 * self.cloud_factor)


def dynamic_price_series(weather: List["DayWeather"], seed: int = 7) -> List[float]:
    """
    Realistic dynamic spot price (EUR/kWh), hour by hour: morning + evening
    peaks, a midday crash when solar floods the grid, shifting day to day with
    the weather. This is the kind of tariff where optimal control beats rules.
    """
    rng = random.Random(seed)
    prices = []
    for day in weather:
        day_scale = rng.uniform(0.85, 1.20)
        for h in range(24):
            base = 0.10
            morning = 0.18 * math.exp(-((h - 8) ** 2) / 4.0)
            evening = 0.28 * math.exp(-((h - 19) ** 2) / 3.0)
            night = -0.04 if (h < 6 or h >= 23) else 0.0
            p = base + morning + evening + night
            if 11 <= h <= 15:                       # midday solar crash
                p -= 0.12 * (1 - day.cloud_factor)
            p = p * day_scale + rng.uniform(-0.015, 0.015)
            prices.append(max(0.0, p))
    return prices


def export_price_series(prices: List[float], fee: float = 0.01) -> List[float]:
    """Export earns the spot price minus a small grid fee (real dynamic tariffs)."""
    return [max(0.0, p - fee) for p in prices]


def generate_month_weather(days: int = 30, seed: int = 42) -> List[DayWeather]:
    """
    A realistic spring/summer month: mix of sunny, partly cloudy, overcast days.
    Seeded so every test run is identical (reproducibility = good engineering).
    """
    rng = random.Random(seed)
    weather = []
    for _ in range(days):
        roll = rng.random()
        if roll < 0.40:
            cloud = rng.uniform(0.0, 0.25)    # sunny day
        elif roll < 0.75:
            cloud = rng.uniform(0.25, 0.60)   # partly cloudy
        else:
            cloud = rng.uniform(0.60, 0.95)   # overcast
        weather.append(DayWeather(cloud_factor=cloud))
    return weather


# ── Derived facts (used by Test 1 to sanity-check) ───────────────────────────

def daily_load_kwh() -> float:
    return sum(LOAD_PROFILE_KW)  # each value is kW held for 1 hour = kWh

def peak_load_kw() -> float:
    return max(LOAD_PROFILE_KW)

def average_load_kw() -> float:
    return sum(LOAD_PROFILE_KW) / 24

def clear_day_solar_kwh() -> float:
    return sum(clear_sky_kw(h) for h in range(24))


# ── FacilityConfig — one facility's parameters as a single object ─────────────
# This is what turns the engine from "one hard-coded factory" into "any user's
# facility." Every field defaults to the module constant above, so
# FacilityConfig() == today's default factory (behaviour is byte-identical).
# A per-user request just builds a FacilityConfig with different numbers and
# hands it to the same validated engine.
@dataclass
class FacilityConfig:
    name: str = "Default factory"
    latitude: float = 48.137          # Munich (only used by the estimate layer)
    longitude: float = 11.575

    # solar
    solar_peak_kw: float = SOLAR_PEAK_KW
    solar_nameplate_kw: float = SOLAR_NAMEPLATE_KW
    sunrise_hour: int = SUNRISE_HOUR
    sunset_hour: int = SUNSET_HOUR

    # battery
    battery_capacity_kwh: float = BATTERY_CAPACITY_KWH
    battery_max_charge_kw: float = BATTERY_MAX_CHARGE_KW
    battery_max_discharge_kw: float = BATTERY_MAX_DISCHARGE_KW
    battery_min_soc: float = BATTERY_MIN_SOC
    battery_max_soc: float = BATTERY_MAX_SOC
    charge_efficiency: float = CHARGE_EFFICIENCY
    discharge_efficiency: float = DISCHARGE_EFFICIENCY

    # grid
    grid_max_kw: float = GRID_MAX_KW

    # tariff
    peak_tariff: float = PEAK_TARIFF
    offpeak_tariff: float = OFFPEAK_TARIFF
    feed_in_tariff: float = FEED_IN_TARIFF
    peak_start: int = PEAK_START
    peak_end: int = PEAK_END

    # grid carbon intensity
    co2_peak: float = CO2_PEAK
    co2_offpeak: float = CO2_OFFPEAK

    # hourly load profile (kW)
    load_profile_kw: List[float] = field(default_factory=lambda: list(LOAD_PROFILE_KW))

    # ── helpers (same logic as the module functions, but per-config) ─────────
    def is_peak(self, hour: int) -> bool:
        return self.peak_start <= hour < self.peak_end

    def tariff(self, hour: int) -> float:
        return self.peak_tariff if self.is_peak(hour) else self.offpeak_tariff

    def grid_co2(self, hour: int) -> float:
        return self.co2_peak if self.is_peak(hour) else self.co2_offpeak

    def clear_sky_kw(self, hour: int) -> float:
        if self.sunrise_hour <= hour <= self.sunset_hour:
            angle = math.pi * (hour - self.sunrise_hour) / (self.sunset_hour - self.sunrise_hour)
            return self.solar_peak_kw * math.sin(angle)
        return 0.0

    def solar_kwh(self, hour: int, cloud_factor: float) -> float:
        """kWh produced this hour given a cloud factor (0=clear, 1=overcast)."""
        return self.clear_sky_kw(hour) * (1.0 - 0.85 * cloud_factor)


# The default facility (mirrors the module constants exactly).
DEFAULT_CONFIG = FacilityConfig()
