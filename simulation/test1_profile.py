"""
TEST 1 — Is the factory profile realistic?

We print the raw facts about the site and check them against what a real
mid-sized factory looks like, BEFORE simulating anything.
"""

import factory as F


def main():
    print("=" * 60)
    print("TEST 1 — MID-SIZED FACTORY PROFILE")
    print("=" * 60)

    print("\n[INPUT] Hourly load profile (kW):")
    for h in range(24):
        bar = "█" * int(F.LOAD_PROFILE_KW[h] / 3)
        sun = F.clear_sky_kw(h)
        print(f"  {h:02d}:00  {F.LOAD_PROFILE_KW[h]:5.0f} kW  {bar}  (clear-sky solar {sun:4.0f} kW)")

    daily_load = F.daily_load_kwh()
    monthly_load = daily_load * 30
    clear_solar = F.clear_day_solar_kwh()

    print("\n[OUTPUT] Derived facts:")
    print(f"  Average load .............. {F.average_load_kw():6.1f} kW")
    print(f"  Peak load ................. {F.peak_load_kw():6.1f} kW")
    print(f"  Daily consumption ......... {daily_load:6.0f} kWh")
    print(f"  Monthly consumption ....... {monthly_load:6.0f} kWh  ({monthly_load/1000:.1f} MWh)")
    print(f"  Annual consumption ........ {daily_load*365/1000:6.0f} MWh")
    print(f"  Solar (best clear day) .... {clear_solar:6.0f} kWh")
    print(f"  Solar vs load (best day) .. {clear_solar/daily_load*100:6.1f} %")

    print(f"\n  Battery ................... {F.BATTERY_CAPACITY_KWH:.0f} kWh / "
          f"{F.BATTERY_MAX_CHARGE_KW:.0f} kW")
    print(f"  Peak tariff ............... {F.PEAK_TARIFF:.2f} EUR/kWh (07:00-22:00)")
    print(f"  Off-peak tariff ........... {F.OFFPEAK_TARIFF:.2f} EUR/kWh (22:00-07:00)")
    print(f"  Tariff spread ............. {F.PEAK_TARIFF - F.OFFPEAK_TARIFF:.2f} EUR/kWh")

    print("\n[SANITY CHECK]")
    checks = [
        ("Avg load 40-120 kW (mid-sized)", 40 <= F.average_load_kw() <= 120),
        ("Monthly use 30-80 MWh", 30 <= monthly_load/1000 <= 80),
        ("Solar covers 20-60% on best day", 0.20 <= clear_solar/daily_load <= 0.60),
        ("Tariff spread > 0.10 (arbitrage exists)", F.PEAK_TARIFF - F.OFFPEAK_TARIFF > 0.10),
    ]
    for label, ok in checks:
        print(f"  [{'PASS' if ok else 'FAIL'}] {label}")


if __name__ == "__main__":
    main()
