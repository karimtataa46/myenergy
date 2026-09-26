# Defect Log

The at-a-glance record of every bug found in myEnergy. Each row links to its
GitHub issue (full repro steps live there); this file is the dashboard.

**Workflow:** a failing test (or a review) finds a defect → a GitHub issue captures
the detail → a row is added here → the fix lands → a **regression test** locks it
so it can never silently return → the issue is closed.

**Status:** 9 logged, 9 fixed. 2 caught by the automated test suite, 1 by a
scenario experiment, 6 by manual review during development (before the suite
existed which is exactly why the suite is being built now).

### Severity
| Level | Meaning |
|-------|---------|
| **Critical** | Crashes or disables the running app |
| **High** | Crash on a specific / edge input |
| **Medium** | Wrong output or metric, app keeps running |
| **Low** | Cosmetic / minor inconsistency |

### Defects

| ID | Severity | Area | Defect | Found by | Status | Fixed in |
|----|----------|------|--------|----------|--------|----------|
| [#12](https://github.com/karimtataa46/myenergy/issues/12) | Medium | `brain.py` | A battery at or below 15% was never recharged (not at the cheap night rate, not from solar surplus), so it stayed pinned at the floor | **scenario experiment** (sunny vs cloudy simulation); regression: `TestCriticalBattery` | ✅ Fixed | `4db76a1` |
| [#11](https://github.com/karimtataa46/myenergy/issues/11) | Low | `estimate_service.py` | Monthly and annual savings didn't reconcile (€887/mo shown as €10,650/yr, not €10,644) | **automated test** (`test_annual_is_twelve_times_monthly`) | ✅ Fixed | `d08695b` |
| [#10](https://github.com/karimtataa46/myenergy/issues/10) | High | `models.py` | `urgency()` raised `ZeroDivisionError` for a device with `power_draw_kw = 0` | **automated test** (`test_zero_power_does_not_crash`) | ✅ Fixed | `d1592b6` |
| B-06 | Critical | `models.py` | `urgency()` was wrongly decorated `@property` but takes a `current_time` argument → `TypeError` crashed the control loop every tick, blanking `/api/live` | manual review | ✅ Fixed | `62190fc` |
| B-05 | Critical | `main.py` | Control loop dropped the `latest_snapshot = snap` publish line → `/api/live` returned `{}` permanently (dead dashboard) | manual debugging | ✅ Fixed | `62190fc` |
| B-04 | Medium | `main.py` | `zones` summed to the base load only while `consumption_kw` included shiftable load → dashboard breakdown didn't reconcile with the total | manual review | ✅ Fixed | `62190fc` |
| B-03 | Medium | `simulation/engine.py` | `Totals.solar_fraction` could exceed 100% (no clamp) | code review | ✅ Fixed | `62190fc` |
| B-02 | Medium | `estimate_service.py` | `saved_pct` sign inverted for a net-exporter facility (negative baseline made a real saving read negative) | code review | ✅ Fixed | `62190fc` |
| B-01 | Medium | `weather.py` | Synthetic forecast anchored at `now` instead of midnight, dropping pre-noon hours → battery never charged in the offline fallback | code review | ✅ Fixed | `62190fc` |

_Newest first. Add each new defect at the top._
