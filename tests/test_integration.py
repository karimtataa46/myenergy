"""
T2 — integration tests.

These exercise REAL service code end to end (pricing table + simulation engine +
optimiser + forecast), with only the two Open-Meteo HTTP calls mocked (the
`mock_network` fixture). They catch bugs in the WIRING between components that
unit tests can't see.
"""
import estimate_service
import facility_live


class TestEstimateService:
    """estimate_service.estimate_savings: geocode -> tariff -> engine -> result."""

    def test_returns_expected_shape(self, mock_network):
        result = estimate_service.estimate_savings("Munich", 100, 200, 46920)
        assert result["city"] == "Munich"
        assert result["country"] == "Germany"
        for key in ("saved_eur", "annual_eur", "baseline_eur", "myenergy_eur", "co2_avoided_kg"):
            assert key in result
        assert isinstance(result["saved_eur"], (int, float))

    def test_annual_is_twelve_times_monthly(self, mock_network):
        result = estimate_service.estimate_savings("Munich", 100, 200, 46920)
        assert result["annual_eur"] == round(result["saved_eur"] * 12)

    def test_unknown_city_returns_error(self, mock_network):
        result = estimate_service.estimate_savings("   ", 100, 200, 46920)
        assert "error" in result

    def test_build_facility_uses_country_tariff(self, mock_network):
        cfg, place, tariff = estimate_service.build_facility("Munich", 100, 200, 46920)
        assert place.country_code == "DE"
        assert tariff.peak == 0.45              # Germany's peak price from the table
        assert cfg.solar_nameplate_kw == 100


class TestFacilityLiveSession:
    """facility_live: start a per-user session, then poll its live state."""

    def test_start_then_live_returns_state(self, mock_network):
        sid = facility_live.start("Munich", 100, 200, 46920)
        assert sid is not None
        state = facility_live.live(sid)
        assert state is not None
        assert state["facility"] == "Munich"
        assert 0 <= state["battery_soc"] <= 100
        assert state["solar_kw"] >= 0

    def test_unknown_session_returns_none(self, mock_network):
        assert facility_live.live("does-not-exist") is None

    def test_unknown_city_returns_no_session(self, mock_network):
        assert facility_live.start("   ", 100, 200, 46920) is None
