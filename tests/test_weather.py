"""
T1 (remainder) — unit tests for weather.py pure functions:
the offline synthetic forecast, the Open-Meteo parser, and the forecast queries.
"""
from datetime import datetime, timezone, timedelta

import pytest
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


# ── Never plan with made-up weather (#39) ────────────────────────────────────

BRIGHT_SKY = {"weather": [
    {"timestamp": "2026-10-08T11:00:00+02:00", "solar": 0.214, "cloud_cover": 100, "temperature": 9.5},
    {"timestamp": "2026-10-08T12:00:00+02:00", "solar": 0.261, "cloud_cover": 100, "temperature": 10.1},
]}


def _fail(*a, **k):
    raise OSError("unreachable")


class TestRealForecastOnly:
    def test_reads_the_dwd_forecast_from_bright_sky(self):
        import weather
        from datetime import datetime, timezone
        hours = weather._parse_bright_sky(BRIGHT_SKY)
        assert hours[0].timestamp == datetime(2026, 10, 8, 9, tzinfo=timezone.utc)      # UTC
        assert hours[0].solar_irradiance_wm2 == pytest.approx(214)                       # kWh/m2 per hour -> W/m2
        assert hours[0].cloud_cover_percent == 100
        assert hours[0].estimated_solar_kw == pytest.approx(weather.irradiance_to_solar_kw(214))

    def test_when_open_meteo_fails_the_dwd_answers(self, monkeypatch):
        import weather
        monkeypatch.setattr(weather, "fetch_open_meteo", _fail)
        monkeypatch.setattr(weather, "fetch_dwd", lambda lat, lon: weather._parse_bright_sky(BRIGHT_SKY))
        hours, source = weather.fetch_real_forecast()
        assert source == weather.SOURCE_DWD and len(hours) == 2

    def test_with_no_source_it_says_why_instead_of_inventing_weather(self, monkeypatch):
        import weather
        monkeypatch.setattr(weather, "fetch_open_meteo", _fail)
        monkeypatch.setattr(weather, "fetch_dwd", _fail)
        with pytest.raises(weather.ForecastUnavailable) as e:
            weather.fetch_real_forecast()
        assert "Open-Meteo" in str(e.value) and "DWD" in str(e.value)

    def test_the_developer_estimates_still_fall_back_to_the_clear_sky_model(self, monkeypatch):
        import weather
        monkeypatch.setattr(weather, "fetch_open_meteo", _fail)
        monkeypatch.setattr(weather, "fetch_dwd", _fail)
        assert len(weather.fetch_forecast()) == 48


class TestLivePlantWithoutWeather:
    def _refresh(self, monkeypatch, fetch):
        import asyncio
        from concurrent.futures import ThreadPoolExecutor
        import main
        import weather
        monkeypatch.setattr(weather, "fetch_real_forecast", fetch)
        # Its own thread: the browser tests leave an event loop running in this one.
        with ThreadPoolExecutor(1) as pool:
            pool.submit(asyncio.run, main._refresh_forecast()).result()
        return main

    def test_a_failed_refresh_keeps_the_last_real_forecast(self, monkeypatch):
        import main
        import weather
        real = weather._parse_bright_sky(BRIGHT_SKY)
        monkeypatch.setattr(main, "forecast_cache", real)
        monkeypatch.setattr(main, "forecast_source", weather.SOURCE_DWD)
        monkeypatch.setattr(main, "forecast_error", None)

        def down(*a, **k):
            raise weather.ForecastUnavailable("Open-Meteo: down; DWD: down")
        m = self._refresh(monkeypatch, down)
        assert m.forecast_cache is real and m.forecast_source == weather.SOURCE_DWD
        assert "down" in m.forecast_error

    def test_without_any_forecast_the_plan_says_so(self, client, monkeypatch):
        import main
        import weather
        monkeypatch.setattr(main, "forecast_cache", [])

        def down(*a, **k):
            raise weather.ForecastUnavailable("Open-Meteo: down; DWD: down")
        self._refresh(monkeypatch, down)
        d = client.get("/api/plan").json()
        assert d["available"] is False and "safe rules" in d["message"]
        assert "DWD: down" in d["forecast_error"]
        assert main.forecast_cache == []                     # nothing invented

    def test_the_plan_names_its_weather_source(self, client):
        assert client.get("/api/plan").json()["forecast_source"] == "test forecast"
