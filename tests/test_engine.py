"""
T1 (remainder) — unit tests for the simulation engine physics.

The engine's contract: it enforces energy conservation at the AC bus, battery
rate limits, SOC bounds, and round-trip efficiency. These tests pin those
invariants directly (no need for exact config numbers — they read them off the
config), which is how you test physics robustly.
"""
import pytest

import factory as F
from engine import _apply_battery, step, simulate, StepState, Totals
from controllers import reactive

CFG = F.DEFAULT_CONFIG
CAP = CFG.battery_capacity_kwh
MIN_KWH = CFG.battery_min_soc * CAP
MAX_KWH = CFG.battery_max_soc * CAP
EPS = 1e-6


def make_state(hour=12, solar=0.0, load=50.0, soc=None):
    return StepState(
        hour=hour, solar_kwh=solar, load_kwh=load,
        soc_kwh=0.5 * CAP if soc is None else soc, capacity_kwh=CAP,
        forecast_next_solar_kwh=0.0, forecast_tomorrow_deficit_kwh=0.0, cfg=CFG)


def noop(_state):          # a controller that never touches the battery
    return 0.0


class TestApplyBattery:
    def test_charge_respects_rate_limit(self):
        ac, _ = _apply_battery(0.5 * CAP, 1e6, CFG)          # ask to charge a huge amount
        assert ac <= CFG.battery_max_charge_kw + EPS

    def test_discharge_respects_rate_limit(self):
        ac, _ = _apply_battery(0.9 * CAP, -1e6, CFG)
        assert ac >= -CFG.battery_max_discharge_kw - EPS

    def test_soc_never_exceeds_max(self):
        ac, new = _apply_battery(MAX_KWH, 1e6, CFG)          # already full
        assert new <= MAX_KWH + EPS
        assert ac == pytest.approx(0.0, abs=EPS)             # no room to charge

    def test_soc_never_below_reserve(self):
        ac, new = _apply_battery(MIN_KWH, -1e6, CFG)         # already at reserve
        assert new >= MIN_KWH - EPS
        assert ac == pytest.approx(0.0, abs=EPS)             # nothing to discharge

    def test_charge_applies_efficiency(self):
        soc0 = 0.5 * CAP
        ac, new = _apply_battery(soc0, 10.0, CFG)            # 10 kWh in at the AC bus
        assert new - soc0 == pytest.approx(ac * CFG.charge_efficiency)

    def test_charging_raises_soc_discharging_lowers(self):
        soc0 = 0.5 * CAP
        _, up = _apply_battery(soc0, 10.0, CFG)
        _, down = _apply_battery(soc0, -10.0, CFG)
        assert up > soc0 > down


class TestStepEnergyBalance:
    @pytest.mark.parametrize("solar, load", [(0, 50), (80, 20), (30, 30), (0, 0)])
    def test_ac_bus_conserves_energy(self, solar, load):
        res = step(make_state(solar=solar, load=load), noop)
        # solar + import - export == load + battery_ac  (the engine's guarantee)
        assert res.solar_kwh + res.grid_import_kwh - res.grid_export_kwh == pytest.approx(
            res.load_kwh + res.battery_ac_kwh, abs=1e-3)

    def test_never_imports_and_exports_at_once(self):
        res = step(make_state(solar=80, load=20), noop)
        assert res.grid_import_kwh == 0 or res.grid_export_kwh == 0

    def test_surplus_solar_is_exported(self):
        res = step(make_state(solar=80, load=20), noop)
        assert res.grid_export_kwh > 0
        assert res.grid_import_kwh == 0


class TestSolarFraction:
    def test_clamped_to_one_when_solar_exceeds_load(self):
        assert Totals(solar_used_kwh=500, load_kwh=100).solar_fraction == 1.0

    def test_zero_when_no_solar_used(self):
        assert Totals(solar_used_kwh=0, load_kwh=100).solar_fraction == 0.0

    def test_zero_load_does_not_divide_by_zero(self):
        assert Totals(solar_used_kwh=50, load_kwh=0).solar_fraction == 0.0


class TestSimulate:
    def test_runs_a_two_day_month_with_sane_totals(self):
        weather = F.generate_month_weather(days=2, seed=42)
        totals = simulate(weather, reactive, cfg=CFG)
        assert len(totals.steps) == 2 * 24
        assert totals.grid_import_kwh >= 0
        assert totals.load_kwh > 0
        assert 0.0 <= totals.solar_fraction <= 1.0
