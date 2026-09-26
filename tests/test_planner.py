"""
Unit tests for the forecast planner (planner.py), the decision entry point
(energy_manager.py), and the live loop's hourly forecast (main._planning_forecast).

Scenario used below: it's 05:00 (cheap rate until 07:00), the battery sits at its
20% reserve, and the factory draws a steady 20 kW. What changes is the sun.
"""
from datetime import datetime, timezone, timedelta

import pytest

import brain
import energy_manager
import factory as F
import planner
from engine import HORIZON_HOURS
from models import PlanningForecast, WeatherForecastHour

CFG = F.DEFAULT_CONFIG
RESERVE, FULL = brain.BATTERY_RESERVE_SOC / 100, brain.BATTERY_FULL_SOC / 100
LOAD = [20.0] * HORIZON_HOURS
SUNNY_MORNING = [0, 20, 80, 90, 90, 80, 60, 30] + [0] * (HORIZON_HOURS - 8)
NO_SUN = [0.0] * HORIZON_HOURS


def plan(battery, solar, hour=5, load=LOAD):
    return planner.make_plan(battery, PlanningForecast(hour, solar, load), CFG, RESERVE, FULL)


class TestPlannerDecisions:
    def test_waits_for_the_sun_instead_of_buying(self, make_battery):
        p = plan(make_battery(soc=20), SUNNY_MORNING)
        assert p.grid_charge_now_kw < 0.5              # buys nothing now
        assert p.solar_to_battery_kwh > 50             # because the sun will fill it
        assert p.reason.startswith("Waiting for the sun")

    def test_buys_at_the_cheap_rate_before_a_sunless_day(self, make_battery):
        p = plan(make_battery(soc=20), NO_SUN)
        assert p.grid_charge_now_kw > 0.5
        assert p.reason.startswith("Buying")

    def test_never_plans_below_the_reserve(self, make_battery):
        # peak hour, heavy load, no sun: it may discharge only down to 20%
        p = plan(make_battery(soc=25), NO_SUN, hour=12, load=[80.0] * HORIZON_HOURS)
        max_discharge = (0.25 - RESERVE) * 200 * CFG.discharge_efficiency
        assert p.battery_kw >= -max_discharge - 0.1

    def test_no_forecast_hours_means_no_plan(self, make_battery):
        assert plan(make_battery(soc=50), [], load=[]) is None


class TestEnergyManager:
    def test_without_a_forecast_it_falls_back_to_the_rules(self, make_input):
        inp = make_input(base=27, soc=60, tariff=0.12)
        got, rules = energy_manager.decide(inp, None, CFG), brain.decide(inp)
        assert (got.action, got.battery_kw, got.grid_kw, got.reason) == \
               (rules.action, rules.battery_kw, rules.grid_kw, rules.reason)

    def test_with_a_forecast_the_plan_decides(self, make_input):
        inp = make_input(base=20, soc=20, tariff=0.12)
        d = energy_manager.decide(inp, PlanningForecast(5, SUNNY_MORNING, LOAD), CFG)
        assert d.reason.startswith("Waiting for the sun")
        assert d.battery_kw == pytest.approx(0, abs=0.5)


class TestLiveForecast:
    """main._planning_forecast turns the weather forecast into the planner's shape (#2)."""

    def _weather(self, now, hours_before=2, hours_after=40):
        start = now.replace(minute=0, second=0, microsecond=0) - timedelta(hours=hours_before)
        return [WeatherForecastHour(timestamp=start + timedelta(hours=i), solar_irradiance_wm2=0,
                                    cloud_cover_percent=0, temperature_c=20,
                                    estimated_solar_kw=float(i))
                for i in range(hours_before + hours_after)]

    def test_is_hourly_starts_now_and_spans_the_horizon(self):
        import main
        now = datetime.now(timezone.utc)
        fc = main._planning_forecast(self._weather(now), now)
        assert fc.hour == now.hour
        assert len(fc.solar_kwh) == len(fc.load_kwh) == HORIZON_HOURS
        assert fc.solar_kwh[0] == main.facility.scale_to_array(2.0)   # skipped 2 past hours, scaled to our array
        assert fc.solar_kwh == sorted(fc.solar_kwh)    # in time order
        assert fc.load_kwh[0] == main.facility.expected_load_kw(now.hour)

    def test_no_weather_means_no_forecast(self):
        import main
        assert main._planning_forecast([], datetime.now(timezone.utc)) is None
