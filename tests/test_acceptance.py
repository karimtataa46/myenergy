"""
Acceptance tests for the product's core job ("wait for the sun").

The job, stated precisely:
    Store enough energy for the hours the sun won't cover, buy any shortfall in
    the cheapest hours, never buy grid energy the sun would have given for free,
    and never drain the battery below its reserve.

These drive the LIVE decision entry point (energy_manager.decide, which the
running system calls every tick) through two simulated days that differ ONLY in
tomorrow's weather, and check the outcome, not the implementation.
"""
import dataclasses
from datetime import datetime, timezone

import pytest

import brain
import energy_manager
import factory as F
import models
from engine import HORIZON_HOURS, _apply_battery

# A site whose midday solar exceeds its consumption, so the sun CAN charge the
# battery. On a site where it can't, "wait for the sun" is physically impossible.
SITE = dataclasses.replace(
    F.DEFAULT_CONFIG, load_profile_kw=[x * 0.5 for x in F.DEFAULT_CONFIG.load_profile_kw])

RESERVE_PCT = brain.BATTERY_RESERVE_SOC
NIGHT_BEFORE_DAY_2 = set([22, 23] + list(range(24, 31)))     # 22:00 day 1 .. 06:59 day 2
SUNNY, CLOUDY = 0.0, 0.95


def run_two_days(tomorrow_cloud, use_forecast=True, site=SITE):
    """Step the live decision hour by hour; return what happened."""
    weather = [F.DayWeather(cloud_factor=0.5), F.DayWeather(cloud_factor=tomorrow_cloud)]
    solar = [site.solar_kwh(h, day.cloud_factor) for day in weather for h in range(24)]
    load = [site.load_profile_kw[h] for _ in weather for h in range(24)]
    cap = site.battery_capacity_kwh
    now = datetime.now(timezone.utc)

    soc = 0.5 * cap
    out = {"night_grid_charge": 0.0, "peak_grid_charge": 0.0, "cost": 0.0,
           "min_soc_pct": 100.0}
    for t in range(48):
        h = t % 24
        inp = brain.BrainInput(
            solar=models.SolarReading(now, solar[t], 0.0),
            battery=models.BatteryState(now, soc / cap * 100, 0.0, cap,
                                        site.battery_max_charge_kw, site.battery_max_discharge_kw),
            base_load_kw=load[t], shiftable_devices=[],
            upcoming_solar_kw=solar[t + 1] if t + 1 < 48 else 0.0,
            current_tariff_eur_kwh=site.tariff(h),
            peak_price_eur_kwh=site.peak_tariff, offpeak_price_eur_kwh=site.offpeak_tariff)
        forecast = models.PlanningForecast(
            hour=h, solar_kwh=solar[t:t + HORIZON_HOURS], load_kwh=load[t:t + HORIZON_HOURS])

        decision = energy_manager.decide(inp, forecast if use_forecast else None, site)

        battery, soc = _apply_battery(soc, decision.battery_kw, site)    # real physics
        grid = load[t] - solar[t] + battery
        grid_charge = max(0.0, battery - max(solar[t] - load[t], 0.0))

        out["cost"] += max(grid, 0) * site.tariff(h) - max(-grid, 0) * site.feed_in_tariff
        out["min_soc_pct"] = min(out["min_soc_pct"], soc / cap * 100)
        if t in NIGHT_BEFORE_DAY_2:
            out["night_grid_charge"] += grid_charge
        if site.is_peak(h):
            out["peak_grid_charge"] += grid_charge
    return out


@pytest.fixture(scope="module")
def runs():
    return {
        ("sunny", "forecast"): run_two_days(SUNNY),
        ("cloudy", "forecast"): run_two_days(CLOUDY),
        ("sunny", "blind"): run_two_days(SUNNY, use_forecast=False),
        ("cloudy", "blind"): run_two_days(CLOUDY, use_forecast=False),
    }


def test_buys_clearly_less_overnight_before_a_sunny_day(runs):
    sunny = runs[("sunny", "forecast")]["night_grid_charge"]
    cloudy = runs[("cloudy", "forecast")]["night_grid_charge"]
    assert sunny < cloudy - 30, f"sunny {sunny:.0f} kWh vs cloudy {cloudy:.0f} kWh"


@pytest.mark.parametrize("tomorrow", ["sunny", "cloudy"])
def test_cheaper_than_the_forecast_blind_engine(runs, tomorrow):
    planned = runs[(tomorrow, "forecast")]["cost"]
    blind = runs[(tomorrow, "blind")]["cost"]
    assert planned < blind - 1.0, f"with forecast €{planned:.0f} vs blind €{blind:.0f}"


@pytest.mark.parametrize("tomorrow", ["sunny", "cloudy"])
def test_only_buys_battery_energy_in_cheap_hours(runs, tomorrow):
    assert runs[(tomorrow, "forecast")]["peak_grid_charge"] < 0.5


@pytest.mark.parametrize("tomorrow", ["sunny", "cloudy"])
def test_never_drains_below_the_reserve(runs, tomorrow):
    lowest = runs[(tomorrow, "forecast")]["min_soc_pct"]
    assert lowest >= RESERVE_PCT - 0.5, f"lowest battery {lowest:.1f}% < reserve {RESERVE_PCT}%"


# ── the demo site must be able to SHOW the feature ────────────────────────────
# Guards against resizing the demo back into a plant whose solar never exceeds
# its load: the logic would still be right, but the dashboard could never show
# "wait for the sun", which is exactly the problem we had with the 100 kWp demo.

def test_demo_site_has_a_midday_solar_surplus():
    import simulator
    cfg = simulator.DEMO_CFG
    best = max(cfg.solar_kwh(h, 0.0) - cfg.load_profile_kw[h] for h in range(24))
    assert best > 20, f"demo's best sunny-hour surplus is only {best:.0f} kW"


def test_demo_site_waits_for_the_sun():
    import simulator
    sunny = run_two_days(SUNNY, site=simulator.DEMO_CFG)["night_grid_charge"]
    cloudy = run_two_days(CLOUDY, site=simulator.DEMO_CFG)["night_grid_charge"]
    assert sunny < cloudy - 30, f"demo: sunny {sunny:.0f} kWh vs cloudy {cloudy:.0f} kWh"
