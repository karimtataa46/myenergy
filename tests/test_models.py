"""
Unit tests for models.ShiftableDevice: fulfilment, urgency, and the min-runtime
locks that Stage 1 of the brain depends on.

Includes boundary and degenerate-input cases (exactly-zero energy, past deadline,
zero power draw) because that is where real bugs hide.
"""
import math
from datetime import datetime, timezone, timedelta

import pytest


class TestFulfilment:
    def test_fulfilled_at_exactly_zero(self, make_device):
        assert make_device(kwh_needed=0).is_fulfilled is True     # boundary

    def test_not_fulfilled_with_energy_left(self, make_device):
        assert make_device(kwh_needed=5).is_fulfilled is False


class TestUrgency:
    def test_zero_when_fulfilled(self, make_device):
        assert make_device(kwh_needed=0).urgency(datetime.now(timezone.utc)) == 0.0

    def test_normal_value(self, make_device):
        # 40 kWh at 10 kW = 4h of work, 8h until deadline -> urgency 0.5
        dev = make_device(power_kw=10, kwh_needed=40, hours_to_deadline=8)
        assert dev.urgency(datetime.now(timezone.utc)) == pytest.approx(0.5, abs=0.02)

    def test_infinite_when_deadline_already_passed(self, make_device):
        dev = make_device(hours_to_deadline=-1)          # deadline in the past
        assert math.isinf(dev.urgency(datetime.now(timezone.utc)))

    def test_zero_power_does_not_crash(self, make_device):
        # A 0 kW device can never make progress. urgency() must not divide by zero.
        dev = make_device(power_kw=0, kwh_needed=5, hours_to_deadline=4)
        assert math.isinf(dev.urgency(datetime.now(timezone.utc)))


class TestMinRuntimeLocks:
    def test_no_last_change_is_never_locked(self, make_device):
        dev = make_device(is_on=True, min_on=10, last_change=None)
        assert dev.locked_on(datetime.now(timezone.utc)) is False

    def test_recently_switched_on_is_locked_on(self, make_device):
        now = datetime.now(timezone.utc)
        dev = make_device(is_on=True, min_on=10, last_change=now)
        assert dev.locked_on(now) is True

    def test_lock_expires_after_min_on_time(self, make_device):
        now = datetime.now(timezone.utc)
        dev = make_device(is_on=True, min_on=10, last_change=now - timedelta(minutes=20))
        assert dev.locked_on(now) is False

    def test_recently_switched_off_is_locked_off(self, make_device):
        now = datetime.now(timezone.utc)
        dev = make_device(is_on=False, min_off=10, last_change=now)
        assert dev.locked_off(now) is True
