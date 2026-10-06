"""
Tests for the day-ahead price source (backend/prices.py) and GET /api/prices (#31).

The real API is never called: `fake_market` (conftest.py) stands in for it.
"""
import io
import json
from datetime import datetime, timedelta, timezone

import pytest

import prices
from conftest import fake_market

NOW = datetime(2026, 10, 6, 12, 30, tzinfo=timezone.utc)     # 14:30 in Munich
HOUR = timedelta(hours=1)


class TestHourly:
    def test_four_quarter_hours_become_one_hourly_average_in_eur_per_kwh(self):
        t0 = int(datetime(2026, 10, 6, 10, tzinfo=timezone.utc).timestamp())
        got = prices.hourly([t0, t0 + 900, t0 + 1800, t0 + 2700, t0 + 3600], [100, 120, 140, 160, 50])
        assert got == [(datetime(2026, 10, 6, 10, tzinfo=timezone.utc), pytest.approx(0.13)),
                       (datetime(2026, 10, 6, 11, tzinfo=timezone.utc), pytest.approx(0.05))]

    def test_missing_values_are_skipped(self):
        t0 = int(datetime(2026, 10, 6, 10, tzinfo=timezone.utc).timestamp())
        assert prices.hourly([t0, t0 + 900], [None, 80]) == [(datetime(2026, 10, 6, 10, tzinfo=timezone.utc), pytest.approx(0.08))]

    def test_fetch_reads_the_api_shape(self, monkeypatch):
        t0 = int(datetime(2026, 10, 6, 10, tzinfo=timezone.utc).timestamp())
        body = json.dumps({"unix_seconds": [t0, t0 + 900], "price": [100, 200], "unit": "EUR / MWh"}).encode()
        seen = []
        monkeypatch.setattr(prices.urllib.request, "urlopen",
                            lambda url, timeout: seen.append(url) or io.BytesIO(body))
        got = prices.fetch_market(NOW.date(), NOW.date() + timedelta(days=1))
        assert got == [(datetime(2026, 10, 6, 10, tzinfo=timezone.utc), pytest.approx(0.15))]
        assert "bzn=DE-LU" in seen[0] and "start=2026-10-06" in seen[0] and "end=2026-10-07" in seen[0]


class TestWhatTheFactoryPays:
    def test_the_factory_pays_the_market_price_plus_fees_and_taxes(self):
        h = prices.to_hour_price(NOW, 0.12)
        assert h.buy == pytest.approx(0.12 + prices.SURCHARGE_EUR_KWH)

    def test_export_earns_the_market_price_minus_a_fee(self):
        assert prices.to_hour_price(NOW, 0.12).sell == pytest.approx(0.12 - prices.EXPORT_FEE_EUR_KWH)

    def test_a_negative_market_price_never_makes_export_cost_money(self):
        h = prices.to_hour_price(NOW, -0.03)
        assert h.sell == 0.0
        assert h.buy == pytest.approx(-0.03 + prices.SURCHARGE_EUR_KWH)   # but buying gets cheaper


class TestPriceBook:
    def book(self, fetch=fake_market):
        b = prices.PriceBook(fetch=fetch)
        b.refresh(NOW)
        return b

    def test_starts_at_the_current_hour_and_covers_the_horizon(self):
        hours = self.book().next_hours(NOW, 36)
        assert len(hours) == 36
        assert hours[0].start == NOW.replace(minute=0)
        assert all(b.start - a.start == HOUR for a, b in zip(hours, hours[1:]))

    def test_published_hours_are_real_and_later_ones_are_estimated_from_a_day_earlier(self):
        def until_tomorrow_night(first, last):          # tomorrow's prices are published, the day after isn't
            return fake_market(first, last)
        hours = self.book(until_tomorrow_night).next_hours(NOW, 60)
        real = [h for h in hours if not h.estimated]
        estimated = [h for h in hours if h.estimated]
        assert real and estimated and max(h.start for h in real) < min(h.start for h in estimated)
        e = estimated[0]
        same_hour_yesterday = next(h for h in real if h.start == e.start - timedelta(days=1))
        assert e.market == same_hour_yesterday.market

    def test_says_where_the_prices_come_from(self):
        b = self.book()
        assert b.source == prices.SOURCE_REAL and b.fetched_at == NOW

    def test_offline_it_falls_back_to_simulated_prices_and_says_so(self):
        def offline(first, last):
            raise OSError("no network")
        b = self.book(offline)
        assert b.source == prices.SOURCE_SIMULATED
        assert len(b.next_hours(NOW, 36)) == 36

    def test_a_failed_refresh_keeps_the_real_prices(self):
        b = self.book()
        b._fetch = lambda first, last: (_ for _ in ()).throw(OSError("no network"))
        b.refresh(NOW + HOUR)
        assert b.source == prices.SOURCE_REAL and b.fetched_at == NOW


class TestEndpoint:
    def test_lists_the_next_hours_with_their_source(self, client):
        d = client.get("/api/prices").json()
        assert d["source"] == prices.SOURCE_REAL
        assert d["surcharge_eur_kwh"] == prices.SURCHARGE_EUR_KWH
        assert len(d["hours"]) == 36
        h = d["hours"][0]
        assert {"time", "label", "market", "buy", "sell", "estimated"} <= h.keys()
        assert len(h["label"]) == 5 and h["label"][2] == ":"
        assert all(x["buy"] > x["market"] for x in d["hours"])
