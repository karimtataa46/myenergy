"""
Estimate service — the FACADE for per-user savings.

One entry point, estimate_savings(...), hides all the coordination behind a
single clean call:

    city  ─▶ pricing_service   (country price + grid carbon + coordinates)
          ─▶ weather pattern
          ─▶ build a FacilityConfig from the user's numbers
          ─▶ run the validated engine (optimiser vs dumb baseline)
          ─▶ assemble the result

The API layer just calls this; it never touches the subsystems directly.
"""

import sys
import os

# Make the validated simulation engine importable
_SIM = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "simulation"))
if _SIM not in sys.path:
    sys.path.insert(0, _SIM)

import factory as F           # noqa: E402
from engine import simulate   # noqa: E402
from controllers import reactive  # noqa: E402
from optimizer import optimal     # noqa: E402
import pricing_service as pricing  # noqa: E402

DAYS = 30
_BASE_MONTHLY_KWH = sum(F.LOAD_PROFILE_KW) * DAYS   # default profile's monthly total


def _sunshine_factor(latitude: float) -> float:
    """
    Rough location sun scaling: sunnier nearer the equator. 1.0 at ~48°N
    (Munich baseline). Approximate — a real product would use the site's
    measured irradiance history.
    """
    lat = abs(latitude)
    return max(0.65, min(1.25, 1.0 + (48 - lat) * 0.0125))


def build_facility(city: str, solar_kwp: float, battery_kwh: float,
                   monthly_kwh: float, place=None):
    """
    Turn simple user inputs into a FacilityConfig + resolved Place + tariff.
    Returns (cfg, place, tariff) or (None, None, None) if the city is unknown.
    Shared by the one-shot estimate AND the live facility dashboard. If `place`
    is provided (from an autocomplete pick) we use its exact coordinates and
    country instead of re-geocoding the typed name.
    """
    if place is not None:
        tariff = pricing.tariff_for_country(place.country_code)
    else:
        place, tariff = pricing.lookup(city)
    if place is None:
        return None, None, None

    solar_kwp = max(0.0, float(solar_kwp or 0))
    battery_kwh = max(1.0, float(battery_kwh or 0))       # need a battery to optimise
    monthly_kwh = max(100.0, float(monthly_kwh or _BASE_MONTHLY_KWH))

    # scale the realistic default load SHAPE to match the user's monthly total
    load_scale = monthly_kwh / _BASE_MONTHLY_KWH
    load_profile = [round(v * load_scale, 3) for v in F.LOAD_PROFILE_KW]

    # solar: nameplate kWp -> realistic clear-sky peak (~0.62×), scaled by location
    solar_peak = 0.62 * solar_kwp * _sunshine_factor(place.latitude)

    # battery power ≈ C/4 (like the default 50 kW for 200 kWh); grid cap from load
    rate = max(2.0, battery_kwh / 4.0)
    grid_max = max(50.0, max(load_profile) * 2.5)

    cfg = F.FacilityConfig(
        name=place.name, latitude=place.latitude, longitude=place.longitude,
        solar_peak_kw=solar_peak, solar_nameplate_kw=solar_kwp,
        battery_capacity_kwh=battery_kwh,
        battery_max_charge_kw=rate, battery_max_discharge_kw=rate,
        grid_max_kw=grid_max,
        peak_tariff=tariff.peak, offpeak_tariff=tariff.offpeak,
        feed_in_tariff=tariff.feed_in,
        co2_peak=tariff.co2_peak, co2_offpeak=tariff.co2_offpeak,
        load_profile_kw=load_profile,
    )
    return cfg, place, tariff


def estimate_savings(city: str, solar_kwp: float, battery_kwh: float,
                     monthly_kwh: float, place=None) -> dict:
    """Compute one facility's monthly savings from simple user inputs."""
    cfg, place, tariff = build_facility(city, solar_kwp, battery_kwh, monthly_kwh, place=place)
    if cfg is None:
        return {"error": f"Couldn't find “{city}”. Try a nearby larger city."}
    solar_kwp = cfg.solar_nameplate_kw
    battery_kwh = cfg.battery_capacity_kwh
    monthly_kwh = sum(cfg.load_profile_kw) * DAYS

    weather = F.generate_month_weather(days=DAYS, seed=42)
    base = simulate(weather, reactive, cfg=cfg)     # dumb baseline
    smart = simulate(weather, optimal, cfg=cfg)     # myEnergy optimiser
    saved = base.cost_eur - smart.cost_eur
    co2 = base.co2_kg - smart.co2_kg

    return {
        "city": place.name,
        "country": place.country,
        "priced": pricing.is_priced(place.country_code),   # real price vs estimate
        "monthly_kwh": round(monthly_kwh),
        "solar_kwp": round(solar_kwp),
        "battery_kwh": round(battery_kwh),
        "price_peak": tariff.peak,
        "price_offpeak": tariff.offpeak,
        "baseline_eur": round(base.cost_eur),
        "myenergy_eur": round(smart.cost_eur),
        "saved_eur": round(saved),
        # Divide by the MAGNITUDE of the baseline so the % follows the sign of
        # the saving. For a net-exporter facility the baseline is negative (it
        # earns money); a positive saving must still read as a positive %.
        "saved_pct": round(saved / abs(base.cost_eur) * 100, 1) if base.cost_eur else 0.0,
        "annual_eur": round(saved * 12),
        "co2_avoided_kg": round(co2),
        "solar_fraction_pct": round(smart.solar_fraction * 100, 1),
    }
