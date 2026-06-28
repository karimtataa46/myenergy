from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict


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
class EnergyDecision:
    timestamp: datetime
    action: GridAction
    reason: str
    solar_kw: float
    battery_kw: float        # positive = charging, negative = discharging
    grid_kw: float           # positive = importing, negative = exporting
    consumption_kw: float
    forecast_horizon_hours: int = 2


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
