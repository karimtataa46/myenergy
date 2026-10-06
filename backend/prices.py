"""
Real German day-ahead electricity prices: what a factory on a dynamic tariff pays.

Source: Energy-Charts (Fraunhofer ISE), with data from Bundesnetzagentur | SMARD.de
under CC BY 4.0. The day-ahead market fixes a price for every 15 minutes of the next
day and publishes it around 13:00 the day before, so tomorrow's prices are known in
advance. Hours that aren't published yet are estimated from the same hour a day
earlier and marked as estimated.

What the factory pays per kWh = market price + SURCHARGE (grid fees, levies and
taxes, which don't change hour by hour). Exported solar earns the market price minus
a small marketing fee, never less than zero.

If the API can't be reached, the simulated price model from the validated
simulation is used instead, and `source` says so.
"""
import json
import os
import sys
import urllib.request
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Callable, Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

_SIM_DIR = os.path.join(os.path.dirname(__file__), "..", "simulation")
if os.path.abspath(_SIM_DIR) not in sys.path:
    sys.path.insert(0, os.path.abspath(_SIM_DIR))
import factory as F   # noqa: E402

API = "https://api.energy-charts.info/price?bzn=DE-LU&start={start}&end={end}"
SOURCE_REAL = "Bundesnetzagentur | SMARD.de (CC BY 4.0), via Energy-Charts"
SOURCE_SIMULATED = "simulated prices (the market prices could not be fetched)"
SITE_TZ = ZoneInfo("Europe/Berlin")

SURCHARGE_EUR_KWH = 0.10    # grid fees, levies and taxes; an assumption for a mid-sized factory
EXPORT_FEE_EUR_KWH = 0.01

Market = List[Tuple[datetime, float]]          # (start of the hour, UTC; EUR/kWh)


@dataclass(frozen=True)
class HourPrice:
    start: datetime          # start of the hour, UTC
    market: float            # day-ahead market price, EUR/kWh
    buy: float               # what the factory pays, EUR/kWh
    sell: float              # what exported solar earns, EUR/kWh
    estimated: bool = False  # not published yet: copied from the same hour a day earlier


def to_hour_price(start: datetime, market: float, estimated: bool = False) -> HourPrice:
    return HourPrice(start, round(market, 4), round(market + SURCHARGE_EUR_KWH, 4),
                     round(max(market - EXPORT_FEE_EUR_KWH, 0.0), 4), estimated)


def hourly(unix_seconds: List[int], eur_per_mwh: List[Optional[float]]) -> Market:
    """15-minute (or hourly) market prices in EUR/MWh -> one average per hour in EUR/kWh."""
    by_hour: Dict[datetime, List[float]] = defaultdict(list)
    for ts, price in zip(unix_seconds, eur_per_mwh):
        if price is None:
            continue
        t = datetime.fromtimestamp(ts, tz=timezone.utc).replace(minute=0, second=0, microsecond=0)
        by_hour[t].append(price / 1000)
    return sorted((t, sum(v) / len(v)) for t, v in by_hour.items())


def fetch_market(first: date, last: date) -> Market:
    """Day-ahead prices for whole local days `first`..`last` (raises on any network error)."""
    url = API.format(start=first.isoformat(), end=last.isoformat())
    with urllib.request.urlopen(url, timeout=8) as r:
        data = json.loads(r.read())
    return hourly(data["unix_seconds"], data["price"])


def simulated_market(start: datetime, hours: int) -> Market:
    """The simulation's price model, as a stand-in when the real prices can't be fetched."""
    first = start.replace(hour=0, minute=0, second=0, microsecond=0)
    days = (hours + start.hour) // 24 + 2
    series = F.dynamic_price_series(F.generate_month_weather(days=days, seed=first.toordinal()))
    return [(first + timedelta(hours=k), p) for k, p in enumerate(series)]


class PriceBook:
    """Holds the known hourly prices and answers 'what does each of the next hours cost?'."""

    def __init__(self, fetch: Optional[Callable[[date, date], Market]] = None):
        self._fetch = fetch                     # None: the real API (looked up at call time)
        self._market: Dict[datetime, float] = {}
        self.source = ""
        self.fetched_at: Optional[datetime] = None

    def refresh(self, now: Optional[datetime] = None) -> None:
        """Fetch today and tomorrow (plant-local days). Keeps what it had if the fetch fails."""
        now = now or datetime.now(timezone.utc)
        today = now.astimezone(SITE_TZ).date()
        try:
            got = (self._fetch or fetch_market)(today - timedelta(days=1), today + timedelta(days=1))
        except Exception:
            got = []
        if got:
            self._market = dict(got)
            self.source = SOURCE_REAL
            self.fetched_at = now
        elif not self._market or self.source == SOURCE_SIMULATED:
            self._market = dict(simulated_market(now, 72))
            self.source = SOURCE_SIMULATED
            self.fetched_at = now

    def next_hours(self, now: datetime, n: int) -> List[HourPrice]:
        """The price of each of the next `n` hours, starting with the current one."""
        start = now.astimezone(timezone.utc).replace(minute=0, second=0, microsecond=0)
        out = []
        for k in range(n):
            t = start + timedelta(hours=k)
            if t in self._market:
                out.append(to_hour_price(t, self._market[t]))
                continue
            back = t - timedelta(days=1)          # not published yet: same hour a day earlier
            while back not in self._market and back > t - timedelta(days=3):
                back -= timedelta(days=1)
            if back not in self._market:
                return out
            out.append(to_hour_price(t, self._market[back], estimated=True))
        return out
