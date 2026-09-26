"""
Simulates real hardware: solar inverter, battery, grid meter, zone meters.
In production this is replaced by the gateway reading actual device data.
"""

import math
import os
import sys
import random
from dataclasses import replace
from datetime import datetime, timezone
from typing import Optional
from zoneinfo import ZoneInfo

from models import SolarReading, BatteryState, GridReading, ConsumptionReading

# Single source of truth for the facility's physical facts (array size, etc.).
_SIM_DIR = os.path.join(os.path.dirname(__file__), "..", "simulation")
if os.path.abspath(_SIM_DIR) not in sys.path:
    sys.path.insert(0, os.path.abspath(_SIM_DIR))
import factory as F   # noqa: E402

# Battery physical config
BATTERY_CAPACITY_KWH = 200.0
BATTERY_MAX_CHARGE_KW = 50.0
BATTERY_MAX_DISCHARGE_KW = 50.0

# Grid tariff schedule (EUR/kWh) — simple peak/off-peak
PEAK_TARIFF = 0.28      # 07:00-22:00
OFFPEAK_TARIFF = 0.12   # 22:00-07:00

# Grid carbon intensity is time-varying (night grid is cleaner). Use the single
# source of truth in the factory profile (CO2_PEAK / CO2_OFFPEAK) rather than a
# flat figure, so the live tally agrees with the validated engine.

# Facility consumption zones
ZONES = {
    "production_line_a": 35.0,   # kW base load
    "production_line_b": 28.0,
    "hvac": 15.0,
    "lighting": 8.0,
    "office": 4.0,
}
TOTAL_BASE_CONSUMPTION_KW = sum(ZONES.values())

# The demo factory's rooftop array. Deliberately bigger than its ~90 kW daytime
# load: with the old 100 kWp array the solar never exceeded the load, so the sun
# could never charge the battery and "wait for the sun" could never be shown.
DEMO_NAME = "Munich demo factory"
DEMO_TIMEZONE = "Europe/Berlin"     # where the plant is; the UI shows times in it
DEMO_SOLAR_KWP = 250.0
# Weather forecasts are computed for a 100 kWp reference array; scale to ours.
_SOLAR_SCALE = DEMO_SOLAR_KWP / F.SOLAR_NAMEPLATE_KW
_SITE_TZ = ZoneInfo(DEMO_TIMEZONE)


def site_hour(dt: datetime) -> int:
    """Hour of day on the PLANT's clock (summer/winter time included). Tariffs,
    the work-day pattern and grid carbon all follow local time, not UTC (#18)."""
    return dt.astimezone(_SITE_TZ).hour


def expected_load_kw(hour: int) -> float:
    """Expected base consumption for an hour of day (production slows at night)."""
    return TOTAL_BASE_CONSUMPTION_KW * (1.0 if 6 <= hour <= 22 else 0.3)


# The demo site as ONE config: the live loop, the forecast planner and the
# month-to-date savings all read this, so every number describes the same plant.
DEMO_CFG = replace(
    F.DEFAULT_CONFIG,
    solar_nameplate_kw=DEMO_SOLAR_KWP,
    solar_peak_kw=F.SOLAR_PEAK_KW * _SOLAR_SCALE,
    load_profile_kw=[expected_load_kw(h) for h in range(24)],
    battery_capacity_kwh=BATTERY_CAPACITY_KWH,
    battery_max_charge_kw=BATTERY_MAX_CHARGE_KW,
    battery_max_discharge_kw=BATTERY_MAX_DISCHARGE_KW,
    peak_tariff=PEAK_TARIFF,
    offpeak_tariff=OFFPEAK_TARIFF,
)


class FacilitySimulator:
    """
    Simulates a manufacturing facility's energy systems over time.
    State evolves each time you call update().
    """

    def __init__(self):
        self.battery_soc = 60.0   # start at 60% charge
        self._co2_saved_total = 0.0
        self._cost_saved_total = 0.0
        self._grid_kwh_total = 0.0
        self._solar_kwh_total = 0.0

    def scale_to_array(self, reference_kw: float) -> float:
        """Convert a forecast for the 100 kWp reference array into our array's kW."""
        return reference_kw * _SOLAR_SCALE

    def get_solar(self, override_kw: Optional[float] = None) -> SolarReading:
        now = datetime.now(timezone.utc)
        if override_kw is not None:
            kw = override_kw
        else:
            kw = self._simulate_solar(now)
        # Irradiance back-calculated for display (per reference-array output)
        irradiance = (kw / _SOLAR_SCALE * 1000) / (556 * 0.18) if kw > 0 else 0
        return SolarReading(
            timestamp=now,
            power_kw=round(kw, 2),
            irradiance_wm2=round(irradiance, 1),
        )

    def get_battery(self) -> BatteryState:
        return BatteryState(
            timestamp=datetime.now(timezone.utc),
            soc_percent=round(self.battery_soc, 1),
            power_kw=0.0,  # updated by brain after decision
            capacity_kwh=BATTERY_CAPACITY_KWH,
            max_charge_kw=BATTERY_MAX_CHARGE_KW,
            max_discharge_kw=BATTERY_MAX_DISCHARGE_KW,
        )

    def expected_load_kw(self, hour: int) -> float:
        """The single source for both the simulated readings and the load forecast."""
        return expected_load_kw(hour)

    def get_consumption(self, now: Optional[datetime] = None) -> ConsumptionReading:
        now = now or datetime.now(timezone.utc)
        scale = self.expected_load_kw(site_hour(now)) / TOTAL_BASE_CONSUMPTION_KW
        noise = random.uniform(0.95, 1.05)
        zones = {k: round(v * scale * noise, 2) for k, v in ZONES.items()}
        return ConsumptionReading(
            timestamp=now,
            total_kw=round(sum(zones.values()), 2),
            zones=zones,
        )

    def get_grid(self, net_import_kw: float) -> GridReading:
        now = datetime.now(timezone.utc)
        tariff = DEMO_CFG.tariff(site_hour(now))
        return GridReading(
            timestamp=now,
            # `+ 0.0` normalises -0.0 → 0.0 so an idle grid never serialises as -0.0
            import_kw=round(max(net_import_kw, 0), 2) + 0.0,
            export_kw=round(max(-net_import_kw, 0), 2) + 0.0,
            tariff_eur_kwh=tariff,
        )

    def apply_decision(self, battery_kw: float, dt_seconds: float = 5.0):
        """
        Apply a battery command (positive=charge, negative=discharge).
        Updates battery SOC based on time elapsed.
        """
        delta_kwh = battery_kw * (dt_seconds / 3600)
        self.battery_soc += (delta_kwh / BATTERY_CAPACITY_KWH) * 100
        self.battery_soc = max(5.0, min(100.0, self.battery_soc))

    def accumulate_stats(self, solar_kw: float, grid_kw: float, dt_seconds: float = 5.0):
        hours = dt_seconds / 3600
        solar_kwh = solar_kw * hours
        grid_kwh = max(grid_kw, 0) * hours

        # Solar that actually stays on site (serves load or charges the battery)
        # is what displaces grid. Solar exported to the grid (grid_kw < 0) does
        # NOT reduce this facility's grid import, so don't credit it here.
        export_kw = max(-grid_kw, 0)
        self_used_solar_kwh = max(solar_kw - export_kw, 0) * hours

        self._solar_kwh_total += solar_kwh
        self._grid_kwh_total += grid_kwh

        hour = site_hour(datetime.now(timezone.utc))

        # CO2 avoided = self-consumed solar × the grid's carbon intensity right
        # now (time-varying: night grid is cleaner). Single source of truth.
        self._co2_saved_total += self_used_solar_kwh * F.grid_co2(hour)

        # Cost saved vs. grid reference price (use current tariff)
        self._cost_saved_total += self_used_solar_kwh * DEMO_CFG.tariff(hour)

    @property
    def co2_saved_kg(self) -> float:
        return round(self._co2_saved_total, 3)

    @property
    def cost_saved_eur(self) -> float:
        return round(self._cost_saved_total, 4)

    @property
    def solar_fraction(self) -> float:
        total = self._solar_kwh_total + self._grid_kwh_total
        return round(self._solar_kwh_total / total, 3) if total > 0 else 0.0

    def _simulate_solar(self, dt: datetime) -> float:
        local = dt.astimezone(_SITE_TZ)
        hour = local.hour + local.minute / 60
        if 6 <= hour <= 20:
            angle = math.pi * (hour - 6) / 14
            # Clear-sky peak of THIS array, from the demo config, so live data
            # matches the forecast and savings models.
            peak = DEMO_CFG.solar_peak_kw + random.uniform(-5, 5)  # slight randomness
            return max(0, peak * math.sin(angle))
        return 0.0
