from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, Optional


class GridAction(str, Enum):
    SOLAR_ONLY = "solar_only"
    BATTERY_DISCHARGE = "battery_discharge"
    GRID_IMPORT = "grid_import"
    BATTERY_CHARGE_FROM_SOLAR = "battery_charge_from_solar"
    BATTERY_CHARGE_FROM_GRID = "battery_charge_from_grid"
    EXPORT_TO_GRID = "export_to_grid"


@dataclass
class SolarReading:
    timestamp: datetime
    power_kw: float          # current solar output
    irradiance_wm2: float    # solar irradiance


@dataclass
class BatteryState:
    timestamp: datetime
    soc_percent: float       # state of charge 0-100
    power_kw: float          # positive = charging, negative = discharging
    capacity_kwh: float      # total capacity
    max_charge_kw: float     # max charge rate
    max_discharge_kw: float  # max discharge rate

    @property
    def energy_available_kwh(self) -> float:
        return (self.soc_percent / 100) * self.capacity_kwh

    @property
    def is_critical(self) -> bool:
        return self.soc_percent < 15

    @property
    def is_full(self) -> bool:
        return self.soc_percent > 95


@dataclass
class GridReading:
    timestamp: datetime
    import_kw: float         # power drawn from grid (positive)
    export_kw: float         # power sent to grid (positive)
    tariff_eur_kwh: float    # current electricity price


@dataclass
class ConsumptionReading:
    timestamp: datetime
    total_kw: float
    zones: Dict[str, float]  # zone_name -> kw


@dataclass
class WeatherForecastHour:
    timestamp: datetime
    solar_irradiance_wm2: float
    cloud_cover_percent: float
    temperature_c: float
    estimated_solar_kw: float  # estimated for this facility's panels


@dataclass
class SystemSnapshot:
    timestamp: datetime
    solar: SolarReading
    battery: BatteryState
    grid: GridReading
    consumption: ConsumptionReading
    decision: EnergyDecision
    co2_saved_kg: float = 0.0
    cost_saved_eur: float = 0.0


@dataclass
class ShiftableDevice:
    """NEW: Represents a flexible load that the brain can turn on or off."""
    id: str
    name: str
    power_draw_kw: float  # How much power it uses when ON
    is_on: bool  # Current state

    # Constraints
    must_finish_by: datetime  # Deadline (e.g., EV must be charged by 07:00 tomorrow)
    remaining_kwh_needed: float  # How much energy is left to fulfill the task
    is_interruptible: bool  # Can we turn it off mid-cycle?

    # Equipment protection — real motors/heaters/chargers can't be switched every
    # few seconds. Once ON, stay on for min_on_minutes; once OFF, wait
    # min_off_minutes before restarting. last_change_at is stamped by the control
    # loop each time the device actually flips state. Defaults = 0 → no locking.
    min_on_minutes: float = 0.0
    min_off_minutes: float = 0.0
    last_change_at: Optional[datetime] = None

    @property
    def is_fulfilled(self) -> bool:
        """True if the device has received all the energy it needs."""
        return self.remaining_kwh_needed <= 0.0

    def _minutes_in_state(self, now: datetime) -> float:
        """Minutes since the device last changed on/off state (inf if never)."""
        if self.last_change_at is None:
            return float('inf')
        return (now - self.last_change_at).total_seconds() / 60.0

    def locked_on(self, now: datetime) -> bool:
        """Recently switched ON — must stay on to avoid short-cycling the hardware."""
        return self.is_on and self._minutes_in_state(now) < self.min_on_minutes

    def locked_off(self, now: datetime) -> bool:
        """Recently switched OFF — must wait before restarting."""
        return (not self.is_on) and self._minutes_in_state(now) < self.min_off_minutes

    def urgency(self, current_time: datetime) -> float:
        """
        Returns a score of how badly this device needs to turn on NOW.
        >= 1.0 means it MUST turn on immediately to finish in time.
        (Not a @property — it takes an argument and is called as urgency(now).)
        """
        if self.is_fulfilled:
            return 0.0

        hours_left = (self.must_finish_by - current_time).total_seconds() / 3600.0

        # If the deadline is now or in the past, it's critically urgent
        if hours_left <= 0:
            return float('inf')

        hours_needed = self.remaining_kwh_needed / self.power_draw_kw
        return hours_needed / hours_left


@dataclass
class EnergyDecision:
    """MODIFIED: Added device_commands to control the shiftable loads."""
    timestamp: datetime
    action: GridAction
    reason: str
    solar_kw: float
    battery_kw: float  # positive = charging, negative = discharging
    grid_kw: float  # positive = importing, negative = exporting
    consumption_kw: float
    device_commands: Dict[str, bool] = field(default_factory=dict)  # NEW: {"ev_charger": True, "water_heater": False}
    forecast_horizon_hours: int = 2
