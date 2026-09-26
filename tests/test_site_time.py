"""
Regression tests for bug #18: the demo plant's tariff and work-day pattern must
follow the plant's LOCAL clock (Munich), not UTC, including summer/winter time.

Instants are fixed so the tests mean the same thing whenever they run:
  21:30 UTC in September = 23:30 in Munich (UTC+2) -> cheap rate, night load
  21:30 UTC in January   = 22:30 in Munich (UTC+1) -> cheap rate, night load
  05:30 UTC in September = 07:30 in Munich          -> peak rate, day load
"""
from datetime import datetime, timedelta, timezone

import pytest

import main
import simulator
from models import WeatherForecastHour
from simulator import DEMO_CFG

SUMMER_2130_UTC = datetime(2026, 9, 26, 21, 30, tzinfo=timezone.utc)
WINTER_2130_UTC = datetime(2026, 1, 15, 21, 30, tzinfo=timezone.utc)
SUMMER_0530_UTC = datetime(2026, 9, 26, 5, 30, tzinfo=timezone.utc)


def weather_hours(now, n=36):
    start = now.replace(minute=0, second=0, microsecond=0)
    return [WeatherForecastHour(timestamp=start + timedelta(hours=i), solar_irradiance_wm2=0,
                                cloud_cover_percent=0, temperature_c=20, estimated_solar_kw=0.0)
            for i in range(n)]


@pytest.mark.parametrize("utc, local_hour", [(SUMMER_2130_UTC, 23), (WINTER_2130_UTC, 22),
                                             (SUMMER_0530_UTC, 7)])
def test_site_hour_is_munich_local_time(utc, local_hour):
    assert simulator.site_hour(utc) == local_hour


def test_planning_forecast_uses_the_local_clock():
    fc = main._planning_forecast(weather_hours(SUMMER_2130_UTC), SUMMER_2130_UTC)
    assert fc.hour == 23                                    # not 21
    assert fc.load_kwh[0] == simulator.expected_load_kw(23)  # night load, not the 90 kW day load


@pytest.mark.parametrize("utc, price", [(SUMMER_0530_UTC, DEMO_CFG.peak_tariff),
                                        (SUMMER_2130_UTC, DEMO_CFG.offpeak_tariff)])
def test_live_tariff_follows_the_local_clock(utc, price):
    assert main._tariff_at(utc) == price


def test_simulated_consumption_follows_the_local_clock():
    night = simulator.FacilitySimulator().get_consumption(now=SUMMER_2130_UTC)
    assert night.total_kw < 0.5 * simulator.TOTAL_BASE_CONSUMPTION_KW   # production slowed at night
