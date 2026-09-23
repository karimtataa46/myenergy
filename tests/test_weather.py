"""
T1 (remainder) — unit tests for weather.py pure functions:
the offline synthetic forecast, the Open-Meteo parser, and the forecast queries.
"""
from datetime import datetime, timezone, timedelta

import weather
from models import WeatherForecastHour


class TestSyntheticForecast:
    def test_returns_48_hours(self):
        assert len(weather._synthetic_forecast(48.0, 11.0)) == 48

    def test_values_are_non_negative(self):
        fc = weather._synthetic_forecast(48.0, 11.0)
        assert all(f.estimated_solar_kw >= 0 for f in fc)
        assert all(f.solar_irradiance_wm2 >= 0 for f in fc)

    def test_location_changes_the_series(self):
        west = [f.estimated_solar_kw for f in weather._synthetic_forecast(0.0, 0.0)]
        east = [f.estimated_solar_kw for f in weather._synthetic_forecast(0.0, 120.0)]
        assert west != east          # solar noon lands at a different UTC hour


class TestParseOpenMeteo:
    def test_parses_hourly_block(self):
        data = {"hourly": {
            "time": ["2026-01-01T00:00", "2026-01-01T12:00"],
            "shortwave_radiation": [0, 500],
            "cloudcover": [10, 20],
            "temperature_2m": [5, 6],
        }}
        out = weather._parse_open_meteo(data)
        assert len(out) == 2
        assert out[1].solar_irradiance_wm2 == 500
        assert out[1].estimated_solar_kw > 0
        assert out[0].estimated_solar_kw == 0


class TestForecastQueries:
    def _series(self):
        now = datetime.now(timezone.utc)
        return [WeatherForecastHour(timestamp=now + timedelta(hours=i),
                solar_irradiance_wm2=0, cloud_cover_percent=0, temperature_c=20,
                estimated_solar_kw=10.0 * i) for i in range(6)]

    def test_upcoming_solar_is_non_negative(self):
        assert weather.get_upcoming_solar(self._series(), from_now_hours=6) >= 0

    def test_upcoming_solar_empty_is_zero(self):
        assert weather.get_upcoming_solar([], from_now_hours=3) == 0.0

    def test_current_solar_none_for_empty_forecast(self):
        assert weather.get_current_solar([]) is None
