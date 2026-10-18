"""
Tests for the savings breakdown on hourly prices (backend/savings.py, #33) and the
simulation pieces it relies on.

The number that matters is what the software adds. These tests pin down that the
layers add up to the real bill, that the solar panels and a simple price rule are
never counted as myEnergy's saving, and that myEnergy is judged with an imperfect
solar forecast and only the prices that were already published.
"""
from datetime import date, datetime, timezone

import pytest

import factory as F
import prices
import savings
from conftest import fake_market
from controllers import price_rule
from engine import StepState, simulate
from optimizer import optimal
from simulator import DEMO_CFG

FIRST = date(2026, 10, 1)
BUY, SELL, SOURCE = prices.daily_prices(FIRST, 7, fetch=fake_market)
WEEK = savings.layers(7, BUY, SELL)


class TestLayers:
    def test_the_layers_add_up_to_the_bill(self):
        parts = (WEEK["saved_by_solar_eur"] + WEEK["saved_by_battery_rule_eur"]
                 + WEEK["saved_by_myenergy_eur"])
        assert WEEK["bill_without_anything_eur"] - parts == pytest.approx(WEEK["bill_eur"], abs=0.05)

    def test_the_panels_are_not_counted_as_the_softwares_saving(self):
        assert WEEK["saved_by_solar_eur"] > 5 * WEEK["saved_by_myenergy_eur"]

    def test_a_simple_price_rule_already_earns_money_with_the_battery(self):
        assert WEEK["saved_by_battery_rule_eur"] > 0

    def test_myenergy_adds_something_on_top_of_the_rule(self):
        assert WEEK["saved_by_myenergy_eur"] > 0 and WEEK["myenergy_pct_of_bill"] > 0

    def test_a_perfect_forecast_would_flatter_the_software(self):
        perfect = savings.layers(7, BUY, SELL, forecast_error=0.0)
        assert perfect["saved_by_myenergy_eur"] >= WEEK["saved_by_myenergy_eur"]


class TestDailyPrices:
    def test_24_prices_per_local_day_with_fees_added(self):
        market = dict(fake_market(FIRST, FIRST))
        assert len(BUY) == len(SELL) == 7 * 24 and SOURCE == prices.SOURCE_REAL
        midnight = datetime(2026, 10, 1, tzinfo=prices.SITE_TZ).astimezone(timezone.utc)
        assert BUY[0] == pytest.approx(market[midnight] + prices.SURCHARGE_EUR_KWH)

    def test_the_clock_change_still_gives_24_hours_a_day(self):
        # 25 October 2026: the clocks go back, the day has 25 hours.
        buy, _, source = prices.daily_prices(date(2026, 10, 24), 3, fetch=fake_market)
        assert len(buy) == 72 and None not in buy and source == prices.SOURCE_REAL

    def test_without_the_price_service_it_uses_simulated_prices_and_says_so(self):
        def offline(first, last):
            raise OSError("no network")
        buy, sell, source = prices.daily_prices(FIRST, 3, fetch=offline)
        assert len(buy) == len(sell) == 72 and source == prices.SOURCE_SIMULATED


class TestMonthToDate:
    def test_reports_this_month_and_a_full_month_on_real_prices(self, monkeypatch):
        monkeypatch.setattr(prices, "fetch_market", fake_market)
        monkeypatch.setattr(savings, "_cache", {})
        d = savings.month_to_date(datetime(2026, 10, 8, 12, tzinfo=timezone.utc))
        assert (d["days_elapsed"], d["days_in_month"], d["month"]) == (8, 31, "October 2026")
        assert d["so_far"].keys() == d["full_month"].keys() == WEEK.keys()
        assert d["prices"] == "real" and d["weather"] == "simulated" and d["forecast_error_pct"] == 15

    def test_a_failed_price_request_is_not_kept(self, monkeypatch):
        monkeypatch.setattr(savings, "_cache", {})
        monkeypatch.setattr(prices, "fetch_market", lambda a, b: (_ for _ in ()).throw(OSError("down")))
        now = datetime(2026, 10, 8, 12, tzinfo=timezone.utc)
        assert savings.month_to_date(now)["prices"] == "simulated"
        monkeypatch.setattr(prices, "fetch_market", fake_market)
        assert savings.month_to_date(now)["prices"] == "real"      # the next request tries again


class TestPriceRule:
    def state(self, price, solar=0.0, soc=40.0):
        day = [0.20] * 8 + [0.30] * 8 + [0.40] * 8
        return StepState(hour=12, solar_kwh=solar, load_kwh=60.0, soc_kwh=soc, capacity_kwh=200.0,
                         forecast_next_solar_kwh=0, forecast_tomorrow_deficit_kwh=0, cfg=DEMO_CFG,
                         buy_price=price, day_buy_prices=day)

    def test_charges_in_the_cheapest_third(self):
        assert price_rule(self.state(0.20)) > 0

    def test_uses_the_battery_in_the_dearest_third(self):
        assert price_rule(self.state(0.40)) < 0

    def test_leaves_it_alone_in_between(self):
        assert price_rule(self.state(0.30)) == 0.0

    def test_always_stores_solar_surplus(self):
        assert price_rule(self.state(0.40, solar=100.0)) == pytest.approx(40.0)


class TestOnlyPublishedPrices:
    def test_before_13_00_tomorrow_is_estimated_from_today(self):
        weather = F.generate_month_weather(days=3, seed=42)
        buy = [0.20 + 0.001 * i for i in range(72)]               # every hour different
        seen = {}

        def spy(s):
            seen[len(seen)] = list(s.forecast_buy_price)
            return 0.0
        simulate(weather, spy, cfg=DEMO_CFG, buy_price=buy, sell_price=[0.0] * 72)
        at_noon, at_one = seen[12], seen[13]
        assert at_noon[:12] == buy[12:24]                          # today: published
        assert at_noon[12:24] == buy[0:12]                         # tomorrow 00-11: same hours today
        assert at_noon[24:36] == buy[12:24]                        # tomorrow 12-23: same hours today
        assert at_one[:35] == buy[13:48]                           # after 13:00 tomorrow is known


class TestForecast:
    weather = F.generate_month_weather(days=3, seed=42)

    def test_without_a_forecast_the_controller_sees_the_real_future(self):
        assert (simulate(self.weather, optimal, cfg=DEMO_CFG).cost_eur
                == simulate(self.weather, optimal, cfg=DEMO_CFG, forecast=self.weather).cost_eur)

    def test_a_forecast_is_reproducible_and_stays_in_range(self):
        a, b = F.forecast_of(self.weather), F.forecast_of(self.weather)
        assert [d.cloud_factor for d in a] == [d.cloud_factor for d in b]
        assert all(0.0 <= d.cloud_factor <= 1.0 for d in F.forecast_of(self.weather, error=2.0))

    def test_a_wrong_forecast_changes_the_decisions(self):
        wrong = F.forecast_of(self.weather, error=0.5)
        assert (simulate(self.weather, optimal, cfg=DEMO_CFG).cost_eur
                != simulate(self.weather, optimal, cfg=DEMO_CFG, forecast=wrong).cost_eur)
