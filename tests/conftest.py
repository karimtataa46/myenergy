"""
Shared pytest fixtures for building decision-engine inputs.

These use the "factory as a fixture" pattern: each fixture returns a small
function you call with only the fields your test cares about. That keeps every
test readable (no repeating the full constructor) and lets fixtures build on
each other (make_input uses make_solar + make_battery).

conftest.py is special: pytest auto-discovers it, so any test in this folder can
just name these fixtures as arguments, no import needed.
"""
from datetime import datetime, timezone, timedelta

import pytest

import models
import brain


@pytest.fixture
def make_solar():
    def _make(kw=0.0):
        return models.SolarReading(
            timestamp=datetime.now(timezone.utc), power_kw=kw, irradiance_wm2=0.0)
    return _make


@pytest.fixture
def make_battery():
    def _make(soc=60.0, capacity=200.0, max_charge=50.0, max_discharge=50.0):
        return models.BatteryState(
            timestamp=datetime.now(timezone.utc), soc_percent=soc, power_kw=0.0,
            capacity_kwh=capacity, max_charge_kw=max_charge, max_discharge_kw=max_discharge)
    return _make


@pytest.fixture
def make_device():
    def _make(id="dev", power_kw=11.0, is_on=False, hours_to_deadline=12.0,
              kwh_needed=40.0, interruptible=True, min_on=0.0, min_off=0.0,
              last_change=None):
        return models.ShiftableDevice(
            id=id, name=id, power_draw_kw=power_kw, is_on=is_on,
            must_finish_by=datetime.now(timezone.utc) + timedelta(hours=hours_to_deadline),
            remaining_kwh_needed=kwh_needed, is_interruptible=interruptible,
            min_on_minutes=min_on, min_off_minutes=min_off, last_change_at=last_change)
    return _make


@pytest.fixture
def make_input(make_solar, make_battery):
    def _make(base=90.0, devices=(), tariff=0.28, solar=0.0, soc=60.0,
              peak=0.28, offpeak=0.12, demand=float("inf"), upcoming=0.0):
        return brain.BrainInput(
            solar=make_solar(solar), battery=make_battery(soc),
            base_load_kw=base, shiftable_devices=list(devices),
            upcoming_solar_kw=upcoming, current_tariff_eur_kwh=tariff,
            peak_price_eur_kwh=peak, offpeak_price_eur_kwh=offpeak,
            demand_target_kw=demand)
    return _make
