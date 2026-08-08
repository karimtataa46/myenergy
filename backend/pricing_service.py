"""
Pricing service (a "service module") — city → country → electricity tariff.

Two responsibilities, both so the user never has to think about prices:

  1. resolve_city(city)  — turn a city name into coordinates + country, using
     Open-Meteo's free geocoding API (same provider as our weather, so one
     lookup gives us BOTH the location for the forecast AND the country).

  2. tariff_for_country(code) — a STATIC reference table (not a database) of
     representative commercial/industrial electricity prices and grid carbon
     intensity per country.

These are honest ballpark averages for an estimate. A real deployment would use
the customer's actual contract or a live spot-price feed.
"""

import json
import urllib.request
import urllib.parse
from dataclasses import dataclass
from typing import Optional


@dataclass
class CountryTariff:
    peak: float          # EUR/kWh, daytime peak
    offpeak: float       # EUR/kWh, night
    feed_in: float       # EUR/kWh paid for export
    co2_peak: float      # kg CO2 / kWh, grid carbon at peak
    co2_offpeak: float   # kg CO2 / kWh, grid carbon off-peak


# Representative commercial/industrial electricity prices (EUR/kWh) and grid
# carbon intensity (kg/kWh), ~2024-25 averages. Peak = daytime, off-peak = night.
_TARIFFS = {
    "DE": CountryTariff(0.45, 0.25, 0.06, 0.38, 0.25),  # Germany — pricey, fossil-ish grid
    "BE": CountryTariff(0.32, 0.18, 0.05, 0.17, 0.12),  # Belgium
    "FR": CountryTariff(0.28, 0.16, 0.05, 0.06, 0.04),  # France — cheap, clean nuclear grid
    "NL": CountryTariff(0.40, 0.22, 0.06, 0.35, 0.24),  # Netherlands
    "ES": CountryTariff(0.26, 0.14, 0.04, 0.19, 0.13),  # Spain
    "IT": CountryTariff(0.40, 0.22, 0.06, 0.28, 0.20),  # Italy
    "GB": CountryTariff(0.35, 0.18, 0.05, 0.23, 0.16),  # United Kingdom
    "PL": CountryTariff(0.24, 0.13, 0.04, 0.65, 0.55),  # Poland — coal-heavy grid
    "AT": CountryTariff(0.30, 0.17, 0.05, 0.15, 0.10),  # Austria
    "PT": CountryTariff(0.22, 0.13, 0.04, 0.18, 0.12),  # Portugal
    "IE": CountryTariff(0.35, 0.19, 0.05, 0.30, 0.22),  # Ireland
    "DK": CountryTariff(0.35, 0.19, 0.05, 0.15, 0.10),  # Denmark
    "SE": CountryTariff(0.16, 0.10, 0.03, 0.04, 0.03),  # Sweden — clean grid
    "NO": CountryTariff(0.13, 0.09, 0.03, 0.03, 0.02),  # Norway — hydro
    "CH": CountryTariff(0.24, 0.15, 0.05, 0.05, 0.04),  # Switzerland
    "US": CountryTariff(0.16, 0.10, 0.03, 0.37, 0.30),  # United States
    "CA": CountryTariff(0.13, 0.09, 0.03, 0.13, 0.10),  # Canada
    "MA": CountryTariff(0.14, 0.10, 0.03, 0.70, 0.62),  # Morocco — fossil grid
}
# EU-ish fallback for any country not in the table.
_DEFAULT = CountryTariff(0.30, 0.17, 0.05, 0.30, 0.22)


def tariff_for_country(country_code: Optional[str]) -> CountryTariff:
    """Return the tariff + grid carbon for a country code (ISO-2), or a fallback."""
    return _TARIFFS.get((country_code or "").upper(), _DEFAULT)


def known_countries() -> list:
    return sorted(_TARIFFS.keys())


@dataclass
class Place:
    name: str
    country: str
    country_code: str
    latitude: float
    longitude: float


def resolve_city(city: str) -> Optional[Place]:
    """
    Turn a city name into coordinates + country via Open-Meteo geocoding.
    Returns None if the city can't be found (caller should ask again).
    """
    if not city or not city.strip():
        return None
    url = "https://geocoding-api.open-meteo.com/v1/search?" + urllib.parse.urlencode(
        {"name": city.strip(), "count": 1, "language": "en", "format": "json"}
    )
    try:
        with urllib.request.urlopen(url, timeout=6) as r:
            data = json.loads(r.read())
    except Exception:
        return None
    results = data.get("results") or []
    if not results:
        return None
    g = results[0]
    return Place(
        name=g.get("name", city),
        country=g.get("country", ""),
        country_code=g.get("country_code", ""),
        latitude=g["latitude"],
        longitude=g["longitude"],
    )


def lookup(city: str):
    """Convenience: city -> (Place, CountryTariff), or (None, None) if not found."""
    place = resolve_city(city)
    if place is None:
        return None, None
    return place, tariff_for_country(place.country_code)
