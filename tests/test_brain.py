"""
Unit tests for brain.decide(): the two-stage decision engine.

Stage 2 has six battery rules (critical protect, solar surplus, off-peak
pre-charge, reserve, peak discharge, last-resort import). Stage 1 schedules the
flexible devices. Each class below pins one behaviour, using boundary values
(SOC at exactly the critical threshold) and equivalence classes (peak vs
off-peak, surplus vs deficit).
"""
from datetime import datetime, timezone

import pytest

import brain
from models import GridAction


class TestCriticalBattery:
    """Rule 1: at or below 15% SOC, protect the battery (never discharge it)."""

    @pytest.mark.parametrize("soc", [5, 10, 15])       # 15 is the boundary (<= 15)
    def test_critical_soc_protects_battery(self, make_input, soc):
        d = brain.decide(make_input(base=90, soc=soc, tariff=0.28))
        assert d.action == GridAction.GRID_IMPORT
        assert d.battery_kw == 0.0
        assert "critical" in d.reason.lower()

    def test_just_above_critical_is_not_protected(self, make_input):
        d = brain.decide(make_input(base=90, soc=16, tariff=0.28))
        assert "critical" not in d.reason.lower()

    # Regression tests for bug #12: "protect" must mean "don't discharge",
    # not "don't charge". A drained battery has to be refilled.

    def test_critical_battery_recharges_at_cheap_rate(self, make_input):
        d = brain.decide(make_input(base=30, soc=10, tariff=0.12))
        assert d.action == GridAction.BATTERY_CHARGE_FROM_GRID
        assert d.battery_kw > 0

    def test_critical_battery_charges_from_solar_surplus(self, make_input):
        d = brain.decide(make_input(base=20, solar=60, soc=10, tariff=0.28))
        assert d.action == GridAction.BATTERY_CHARGE_FROM_SOLAR
        assert d.battery_kw > 0

    def test_below_reserve_refills_even_if_spread_too_thin(self, make_input):
        # Arbitrage alone wouldn't pay here, but an empty battery is a
        # reliability problem, so it still refills to the reserve.
        d = brain.decide(make_input(base=30, soc=10, tariff=0.26, peak=0.28, offpeak=0.26))
        assert d.action == GridAction.BATTERY_CHARGE_FROM_GRID
        assert "reserve" in d.reason.lower()


class TestSolarSurplus:
    """Rule 2: more solar than load -> store it, or export once the battery is full."""

    def test_surplus_charges_the_battery(self, make_input):
        d = brain.decide(make_input(base=20, solar=60, soc=60, tariff=0.28))
        assert d.action == GridAction.BATTERY_CHARGE_FROM_SOLAR
        assert d.battery_kw > 0

    def test_large_surplus_exports_the_remainder(self, make_input):
        d = brain.decide(make_input(base=20, solar=90, soc=60, tariff=0.28))
        assert d.action == GridAction.EXPORT_TO_GRID
        assert d.grid_kw < 0                 # negative grid = exporting

    def test_full_battery_exports_all_surplus(self, make_input):
        d = brain.decide(make_input(base=20, solar=60, soc=96, tariff=0.28))
        assert d.action == GridAction.EXPORT_TO_GRID
        assert d.battery_kw == 0.0


class TestOffPeakCharging:
    """Rule 3: at the cheap rate, pre-charge only if it pays and fits the demand cap."""

    def test_precharges_when_spread_pays(self, make_input):
        d = brain.decide(make_input(base=27, soc=60, tariff=0.12, peak=0.28, offpeak=0.12))
        assert d.action == GridAction.BATTERY_CHARGE_FROM_GRID
        assert d.battery_kw > 0

    def test_skips_charging_when_spread_too_thin(self, make_input):
        d = brain.decide(make_input(base=27, soc=60, tariff=0.26, peak=0.28, offpeak=0.26))
        assert d.action == GridAction.GRID_IMPORT
        assert d.battery_kw == 0.0
        assert "losses+wear" in d.reason

    def test_full_battery_rides_cheap_grid(self, make_input):
        d = brain.decide(make_input(base=27, soc=96, tariff=0.12))
        assert d.action == GridAction.GRID_IMPORT
        assert "full" in d.reason.lower()

    def test_charge_capped_by_demand_ceiling(self, make_input):
        d = brain.decide(make_input(base=27, soc=60, tariff=0.12, demand=40))
        assert d.grid_kw <= 40 + 1e-6        # deficit 27 + charge must stay under 40
        assert d.battery_kw <= 13 + 1e-6


class TestPeakDischarge:
    """Rule 5: at peak with charge to spare, discharge to dodge expensive grid."""

    def test_discharges_at_peak(self, make_input):
        d = brain.decide(make_input(base=90, soc=60, tariff=0.28))
        assert d.action == GridAction.BATTERY_DISCHARGE
        assert d.battery_kw < 0

    def test_discharge_capped_by_inverter_rate(self, make_input):
        d = brain.decide(make_input(base=90, soc=60, tariff=0.28))
        assert d.battery_kw == pytest.approx(-50)     # the 50 kW max_discharge


class TestLastResortImport:
    """Rule 6: at peak but battery down at its reserve, just import."""

    def test_low_soc_at_peak_imports(self, make_input):
        d = brain.decide(make_input(base=90, soc=18, tariff=0.28))
        assert d.action == GridAction.GRID_IMPORT
        assert d.battery_kw == 0.0


class TestDeviceScheduling:
    """Stage 1: when each flexible device should switch on."""

    def test_offpeak_turns_on_optional_device(self, make_input, make_device):
        dev = make_device(id="ev", power_kw=11)
        d = brain.decide(make_input(base=27, devices=[dev], tariff=0.12))
        assert d.device_commands["ev"] is True

    def test_peak_leaves_optional_device_off(self, make_input, make_device):
        dev = make_device(id="ev", power_kw=11)
        d = brain.decide(make_input(base=90, devices=[dev], tariff=0.28))
        assert d.device_commands["ev"] is False

    def test_solar_surplus_powers_device(self, make_input, make_device):
        dev = make_device(id="ev", power_kw=11)
        d = brain.decide(make_input(base=20, solar=60, devices=[dev], tariff=0.28))
        assert d.device_commands["ev"] is True

    def test_demand_cap_defers_optional_device(self, make_input, make_device):
        ev = make_device(id="ev", power_kw=11, hours_to_deadline=12, kwh_needed=40)
        wh = make_device(id="wh", power_kw=15, hours_to_deadline=4, kwh_needed=10)
        d = brain.decide(make_input(base=27, devices=[ev, wh], tariff=0.12, demand=40))
        assert d.device_commands["ev"] is True
        assert d.device_commands["wh"] is False
        assert d.grid_kw <= 40 + 1e-6

    def test_must_run_device_overrides_cap(self, make_input, make_device):
        urgent = make_device(id="u", power_kw=20, kwh_needed=10, hours_to_deadline=0.1)
        d = brain.decide(make_input(base=90, devices=[urgent], tariff=0.28, demand=95))
        assert d.device_commands["u"] is True


class TestFollowPlan:
    """Stage 2 with a planner setpoint: follow it, but inside the safety envelope."""

    def test_follows_a_charge_plan(self, make_input):
        d = brain.decide(make_input(base=27, soc=60, tariff=0.12, planned=30, planned_grid=30,
                                    plan_reason="Buying 30 kW at €0.12"))
        assert d.battery_kw == pytest.approx(30)
        assert d.action == GridAction.BATTERY_CHARGE_FROM_GRID
        assert d.reason == "Buying 30 kW at €0.12"

    def test_charging_from_surplus_is_labelled_solar(self, make_input):
        d = brain.decide(make_input(base=20, solar=60, soc=60, planned=40))
        assert d.action == GridAction.BATTERY_CHARGE_FROM_SOLAR

    def test_never_drains_below_the_reserve(self, make_input):
        d = brain.decide(make_input(base=90, soc=18, planned=-40))
        assert d.battery_kw == 0.0
        assert "safety envelope" in d.reason

    def test_never_discharges_into_the_grid(self, make_input):
        # load is only 20 kW, so discharging 50 kW would export 30 kW of battery
        d = brain.decide(make_input(base=20, soc=60, planned=-50))
        assert d.battery_kw == pytest.approx(-20)
        assert d.grid_kw == pytest.approx(0)

    def test_solar_plan_never_buys_peak_grid_when_the_sun_falls_short(self, make_input):
        # Regression for bug #15. The plan expected enough surplus to store 50 kW
        # from the sun, but live there is only 24 kW. Store the 24, don't buy the
        # other 26 at the peak price.
        d = brain.decide(make_input(base=40, solar=64, soc=60, tariff=0.28, planned=50,
                                    planned_grid=0, plan_reason="Storing 50 kW of free solar surplus"))
        assert d.battery_kw == pytest.approx(24)
        assert d.grid_kw == pytest.approx(0)
        assert d.action == GridAction.BATTERY_CHARGE_FROM_SOLAR
        assert "24 kW" in d.reason

    def test_solver_noise_is_not_a_grid_purchase(self, make_input):
        # Regression for bug #19. The plan meant "charge from the sun", but its grid
        # part is 0.3 kW of rounding noise. Live surplus is only 9 kW: store 9, buy nothing.
        d = brain.decide(make_input(base=90, solar=99, soc=60, tariff=0.28, planned=34,
                                    planned_grid=0.3, plan_reason="Storing 34 kW of free solar surplus"))
        assert d.battery_kw == pytest.approx(9)
        assert d.grid_kw == pytest.approx(0)
        assert d.reason.startswith("Storing 9 kW")

    def test_demand_cap_limits_grid_charging(self, make_input):
        d = brain.decide(make_input(base=27, soc=60, tariff=0.12, planned=50, planned_grid=50,
                                    demand=40))
        assert d.battery_kw == pytest.approx(13)
        assert d.grid_kw <= 40 + 1e-6

    def test_full_battery_is_not_charged(self, make_input):
        d = brain.decide(make_input(base=27, soc=96, tariff=0.12, planned=30))
        assert d.battery_kw == 0.0


class TestMinRuntimeInBrain:
    """Stage 1 respects the device min-runtime locks."""

    def test_locked_off_device_stays_off(self, make_input, make_device):
        now = datetime.now(timezone.utc)
        dev = make_device(id="ev", power_kw=11, is_on=False, min_off=10, last_change=now)
        d = brain.decide(make_input(base=27, devices=[dev], tariff=0.12))
        assert d.device_commands["ev"] is False

    def test_locked_on_device_keeps_running(self, make_input, make_device):
        now = datetime.now(timezone.utc)
        dev = make_device(id="ev", power_kw=11, is_on=True, min_on=10, last_change=now)
        d = brain.decide(make_input(base=90, devices=[dev], tariff=0.28))
        assert d.device_commands["ev"] is True

    def test_deadline_overrides_off_lock(self, make_input, make_device):
        now = datetime.now(timezone.utc)
        dev = make_device(id="ev", power_kw=20, kwh_needed=10, hours_to_deadline=0.1,
                          is_on=False, min_off=10, last_change=now)
        d = brain.decide(make_input(base=27, devices=[dev], tariff=0.28))
        assert d.device_commands["ev"] is True
