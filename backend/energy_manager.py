"""
The single entry point the live system calls every tick to decide what to do.

    decide(inp, forecast, cfg) -> EnergyDecision

It takes the current readings (BrainInput) plus the hourly forecast for the
coming hours (PlanningForecast).

Today it still delegates to the rule engine in brain.py, which ignores the
forecast when it decides whether to charge from the grid. The acceptance tests in
tests/test_acceptance.py describe what it SHOULD do; issue #14 makes them pass by
planning the battery from the forecast.
"""
from typing import Optional

import brain
from models import EnergyDecision, PlanningForecast


def decide(inp: brain.BrainInput, forecast: Optional[PlanningForecast],
           cfg=None) -> EnergyDecision:
    return brain.decide(inp)
