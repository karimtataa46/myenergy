"""
T1 (remainder) — unit tests for pricing_service.py:
the static tariff table, helpers, and the geocoding parser (HTTP mocked).
"""
import json

import pytest

import pricing_service as ps


class TestTariffTable:
    @pytest.mark.parametrize("code", ["DE", "FR", "SY", "US", "MA"])
    def test_known_codes_have_consistent_prices(self, code):
        t = ps.tariff_for_country(code)
        assert t.peak > t.offpeak > 0          # peak always dearer than off-peak
        assert t.feed_in >= 0

    def test_is_priced_true_known_false_unknown(self):
        assert ps.is_priced("DE") is True
        assert ps.is_priced("ZZ") is False
        assert ps.is_priced(None) is False

    def test_known_countries_is_sorted_and_nonempty(self):
        cc = ps.known_countries()
        assert "DE" in cc
        assert cc == sorted(cc)


class TestPlaceFrom:
    def test_builds_a_place_from_a_selection(self):
        p = ps.place_from("Lyon", "France", "FR", 45.7, 4.8)
        assert p.name == "Lyon"
        assert p.country_code == "FR"
        assert p.latitude == 45.7


class TestResolveCity:
    def test_blank_city_returns_none_without_network(self):
        assert ps.resolve_city("   ") is None

    def test_parses_a_geocoding_response(self, monkeypatch):
        fake = {"results": [{"name": "Munich", "country": "Germany",
                             "country_code": "DE", "latitude": 48.1, "longitude": 11.6}]}

        class FakeResp:
            def __enter__(self): return self
            def __exit__(self, *a): return False
            def read(self): return json.dumps(fake).encode()

        monkeypatch.setattr(ps.urllib.request, "urlopen", lambda *a, **k: FakeResp())
        place = ps.resolve_city("Munich")
        assert place.name == "Munich"
        assert place.country_code == "DE"
        assert place.latitude == 48.1
