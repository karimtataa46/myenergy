"""
T0 starter suite — unit tests for a few pure functions.

Purpose: prove the pytest harness works and that modules from BOTH source
folders (backend/ and simulation/) import cleanly. It also demonstrates the
patterns we'll reuse everywhere:
  * one test = one behaviour, named so a failure reads like a sentence
  * @pytest.mark.parametrize = the same test run over many input cases
  * arrange / act / assert
"""

import pytest

import brain             # backend/brain.py
import weather           # backend/weather.py
import pricing_service   # backend/pricing_service.py


class TestArbitrageGate:
    """brain._arbitrage_worthwhile: only cycle the battery if the spread pays."""

    @pytest.mark.parametrize("peak, offpeak, expected", [
        (0.45, 0.25, True),    # wide spread clearly pays
        (0.28, 0.12, True),    # the demo's spread pays
        (0.28, 0.26, False),   # spread too thin once losses + wear are counted
        (0.20, 0.20, False),   # no spread at all
    ])
    def test_worthwhile(self, peak, offpeak, expected):
        assert brain._arbitrage_worthwhile(peak, offpeak) is expected


class TestIrradianceToSolar:
    """weather.irradiance_to_solar_kw: W/m^2 -> kW, clamped to the panel size."""

    def test_zero_irradiance_gives_zero(self):
        assert weather.irradiance_to_solar_kw(0) == 0

    def test_output_never_exceeds_panel_capacity(self):
        # A physically impossible irradiance must clamp, never overshoot.
        assert weather.irradiance_to_solar_kw(100_000) <= weather.PANEL_CAPACITY_KW

    def test_more_sun_means_more_power_below_the_cap(self):
        assert weather.irradiance_to_solar_kw(200) < weather.irradiance_to_solar_kw(400)


class TestTariffLookup:
    """pricing_service.tariff_for_country: real table, sane fallback."""

    def test_known_country_has_sane_prices(self):
        t = pricing_service.tariff_for_country("DE")
        assert t.peak > 0 and t.offpeak > 0
        assert t.peak > t.offpeak          # peak must cost more than off-peak

    def test_unknown_country_falls_back_without_crashing(self):
        t = pricing_service.tariff_for_country("ZZ")   # not a real ISO code
        assert t.peak > 0                   # a sensible default, not an error

    def test_none_input_falls_back(self):
        t = pricing_service.tariff_for_country(None)
        assert t.peak > 0
