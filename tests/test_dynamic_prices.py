"""
Acceptance tests for hourly prices (#32): with a dynamic tariff the plan must buy in
the cheapest hours, never in the dearest, and still wait for the sun when the sun
is the cheaper way to fill the battery.

Scenarios are built by hand so each has one clearly right answer.
"""
from datetime import datetime, timedelta, timezone

import pytest

import energy_manager
import planner
import prices
from conftest import fake_market
from engine import HORIZON_HOURS
from models import PlanningForecast
from simulator import DEMO_CFG

H = HORIZON_HOURS
RESERVE, FULL = 0.20, 0.95


def plan(battery, solar, load, buy, sell=None, hour=12):
    sell = sell or [max(p - 0.30, 0.0) for p in buy]
    return planner.make_plan(battery, PlanningForecast(hour, solar, load, buy, sell), DEMO_CFG, RESERVE, FULL)


class TestBuysInTheCheapestHours:
    def test_only_buys_in_the_price_dip(self, make_battery):
        buy = [0.40] * H
        for k in (3, 4, 5):
            buy[k] = 0.15                                      # a three-hour dip, no sun at all
        p = plan(make_battery(soc=20), [0.0] * H, [60.0] * H, buy)
        bought = {h.offset for h in p.hours if h.grid_buy_kw > 0.5}
        assert bought and bought <= {3, 4, 5}

    def test_never_buys_for_the_battery_in_the_dearest_hours(self, make_battery):
        day = [0.20, 0.18, 0.16, 0.15, 0.17, 0.22, 0.30, 0.38, 0.42, 0.40, 0.33, 0.28,
               0.25, 0.24, 0.27, 0.31, 0.36, 0.45, 0.48, 0.44, 0.37, 0.30, 0.25, 0.22]
        buy = (day * 2)[:H]
        p = plan(make_battery(soc=20), [0.0] * H, [60.0] * H, buy, hour=0)
        assert all(h.grid_buy_kw < 0.5 for h in p.hours if h.dear)
        assert any(h.grid_buy_kw > 0.5 for h in p.hours if h.cheap)

    def test_a_flat_price_gives_no_reason_to_cycle_the_battery(self, make_battery):
        p = plan(make_battery(soc=20), [0.0] * H, [60.0] * H, [0.30] * H)
        assert all(h.grid_buy_kw < 0.5 for h in p.hours)   # storing loses ~10%: never worth it


class TestWaitsForTheSun:
    def scenario(self, make_battery, sunny):
        """22:00, the battery at its reserve, cheap until 08:00, tomorrow sunny from 09:00 or dark.
        One clearly right answer: on a sunny day only the expensive hour before the sun
        (08:00) is worth stored night power; the sun fills the battery for the evening."""
        hours = [(22 + k) % 24 for k in range(H)]
        buy = [0.18 if (h < 8 or h >= 22) else 0.40 for h in hours]
        solar = [(160.0 if 9 <= h <= 15 else 0.0) if sunny else 0.0 for h in hours]
        load = [60.0] * H
        forecast = PlanningForecast(22, solar, load, buy, [max(p - 0.30, 0.0) for p in buy])
        battery = make_battery(soc=20)
        p = energy_manager.plan_for(battery, forecast, DEMO_CFG)
        no_sun = energy_manager.plan_without_sun(battery, forecast, DEMO_CFG)
        return p, planner.summarize(p, lambda k: f"{hours[k]:02d}:00", no_sun)

    def test_a_sunny_tomorrow_means_buying_less_tonight(self, make_battery):
        _, sunny = self.scenario(make_battery, sunny=True)
        _, dark = self.scenario(make_battery, sunny=False)
        assert sunny.buy_tonight_kwh < dark.buy_tonight_kwh - 20
        assert sunny.tone == "sun" and sunny.headline == "Waiting for the sun"
        assert "in the next 24 hours" in sunny.detail

    def test_a_dark_tomorrow_tells_the_buying_story_with_the_price(self, make_battery):
        _, s = self.scenario(make_battery, sunny=False)
        assert s.tone == "buy" and s.headline == "Buying in the cheapest hours"
        assert s.buy_price == pytest.approx(0.18) and "€0.18" in s.detail
        assert s.cheapest_price == pytest.approx(0.18) and s.dearest_price == pytest.approx(0.40)


class TestStory:
    def test_two_separate_buying_windows_are_both_named(self, make_battery):
        buy = [0.40] * H
        for k in (2, 3, 9, 10):
            buy[k] = 0.12
        p = plan(make_battery(soc=20), [0.0] * H, [60.0] * H, buy, hour=0)
        s = planner.summarize(p, lambda k: f"{k:02d}:00")
        assert len(s.windows) == 2
        assert "at 02:00 to 04:00 and 09:00 to 11:00" in s.detail

    def test_price_bands_split_the_day_into_thirds(self):
        cheap, dear = planner.price_bands([float(i) for i in range(24)])
        assert sum(cheap) == 8 and sum(dear) == 8
        assert cheap[:8] == [True] * 8 and dear[-8:] == [True] * 8


class TestLiveSystemUsesThePrices:
    @pytest.fixture
    def book(self, monkeypatch):
        import main
        b = prices.PriceBook(fetch=fake_market)
        b.refresh(datetime.now(timezone.utc))
        monkeypatch.setattr(main, "price_book", b)
        return b

    def _weather(self, now, hours=40):
        from models import WeatherForecastHour
        start = now.replace(minute=0, second=0, microsecond=0)
        return [WeatherForecastHour(timestamp=start + timedelta(hours=i), solar_irradiance_wm2=0,
                                    cloud_cover_percent=0, temperature_c=20, estimated_solar_kw=0.0)
                for i in range(hours)]

    def test_the_forecast_carries_the_price_of_each_hour(self, book):
        import main
        now = datetime.now(timezone.utc)
        fc = main._planning_forecast(self._weather(now), now)
        expected = book.next_hours(now, len(fc.solar_kwh))
        assert fc.buy_price == [p.buy for p in expected] and fc.sell_price == [p.sell for p in expected]

    def test_the_current_price_comes_from_the_market(self, book):
        import main
        now = datetime.now(timezone.utc)
        assert main._tariff_at(now) == book.next_hours(now, 1)[0].buy

    def test_the_safety_rules_get_cheap_and_dear_limits_from_the_prices(self, book):
        import main
        cheap_max, dear_min = main._price_limits(datetime.now(timezone.utc))
        assert cheap_max < dear_min
