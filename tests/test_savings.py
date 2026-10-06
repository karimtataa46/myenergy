"""
Tests for the savings breakdown (backend/savings.py) and the forecast it relies on.

The number that matters is what the software adds. These tests pin down that the
layers add up to the real bill, that the solar panels and the night tariff are
never counted as myEnergy's saving, and that the controller is judged with an
imperfect forecast, not with knowledge of the real future.
"""
import pytest

import factory as F
import savings
from engine import simulate
from optimizer import optimal
from simulator import DEMO_CFG

WEEK = savings.layers(7)


class TestLayers:
    def test_the_layers_add_up_to_the_bill(self):
        parts = (WEEK["saved_by_solar_eur"] + WEEK["saved_by_battery_timer_eur"]
                 + WEEK["saved_by_myenergy_eur"])
        assert WEEK["bill_without_anything_eur"] - parts == pytest.approx(WEEK["bill_eur"], abs=0.05)

    def test_the_panels_are_not_counted_as_the_softwares_saving(self):
        # The panels save money with any controller; the software's share is separate and far smaller.
        assert WEEK["saved_by_solar_eur"] > 10 * WEEK["saved_by_myenergy_eur"]

    def test_a_simple_timer_gets_the_night_tariff_without_any_software(self):
        assert WEEK["saved_by_battery_timer_eur"] > 0

    def test_myenergy_adds_something_on_top_of_the_timer(self):
        assert WEEK["saved_by_myenergy_eur"] > 0
        assert WEEK["myenergy_pct_of_bill"] > 0

    def test_a_perfect_forecast_would_flatter_the_software(self):
        perfect = savings.layers(7, forecast_error=0.0)
        assert perfect["saved_by_myenergy_eur"] >= WEEK["saved_by_myenergy_eur"]


class TestMonthToDate:
    def test_reports_this_month_and_a_full_month(self):
        d = savings.month_to_date()
        assert 1 <= d["days_elapsed"] <= d["days_in_month"]
        assert d["so_far"].keys() == d["full_month"].keys() == WEEK.keys()
        assert d["full_month"]["bill_eur"] > d["so_far"]["bill_eur"] or d["days_elapsed"] >= 30
        assert d["forecast_error_pct"] == 15 and d["weather"] == "simulated"


class TestForecast:
    weather = F.generate_month_weather(days=3, seed=42)

    def test_without_a_forecast_the_controller_sees_the_real_future(self):
        assert (simulate(self.weather, optimal, cfg=DEMO_CFG).cost_eur
                == simulate(self.weather, optimal, cfg=DEMO_CFG, forecast=self.weather).cost_eur)

    def test_a_forecast_is_reproducible_and_stays_in_range(self):
        a, b = F.forecast_of(self.weather), F.forecast_of(self.weather)
        assert [d.cloud_factor for d in a] == [d.cloud_factor for d in b]
        assert all(0.0 <= d.cloud_factor <= 1.0 for d in F.forecast_of(self.weather, error=2.0))

    def test_a_forecast_with_no_error_is_the_weather(self):
        assert [d.cloud_factor for d in F.forecast_of(self.weather, error=0.0)] == \
               [d.cloud_factor for d in self.weather]

    def test_a_wrong_forecast_changes_the_decisions(self):
        wrong = F.forecast_of(self.weather, error=0.5)
        assert (simulate(self.weather, optimal, cfg=DEMO_CFG).cost_eur
                != simulate(self.weather, optimal, cfg=DEMO_CFG, forecast=wrong).cost_eur)
