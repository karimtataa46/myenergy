"""
SQLite storage for energy readings and decisions.
Keeps last 24 hours of 5-second snapshots (~17k rows max).
"""

import sqlite3
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data" / "myenergy.db"
RETENTION_HOURS = 24


def init_db():
    DB_PATH.parent.mkdir(exist_ok=True)
    with _conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT NOT NULL,
                solar_kw REAL,
                battery_soc REAL,
                battery_kw REAL,
                grid_import_kw REAL,
                grid_export_kw REAL,
                consumption_kw REAL,
                zones TEXT,
                action TEXT,
                reason TEXT,
                co2_saved_kg REAL,
                cost_saved_eur REAL,
                solar_fraction REAL,
                upcoming_solar_kw REAL
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_ts ON snapshots(ts)")


def insert_snapshot(snap: dict):
    with _conn() as conn:
        conn.execute("""
            INSERT INTO snapshots (
                ts, solar_kw, battery_soc, battery_kw,
                grid_import_kw, grid_export_kw, consumption_kw,
                zones, action, reason, co2_saved_kg, cost_saved_eur,
                solar_fraction, upcoming_solar_kw
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            snap["ts"], snap["solar_kw"], snap["battery_soc"], snap["battery_kw"],
            snap["grid_import_kw"], snap["grid_export_kw"], snap["consumption_kw"],
            json.dumps(snap["zones"]), snap["action"], snap["reason"],
            snap["co2_saved_kg"], snap["cost_saved_eur"],
            snap["solar_fraction"], snap["upcoming_solar_kw"],
        ))
        # Prune old data
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=RETENTION_HOURS)).isoformat()
        conn.execute("DELETE FROM snapshots WHERE ts < ?", (cutoff,))


def get_recent(limit: int = 720) -> list[dict]:
    """Returns last N snapshots, newest first."""
    with _conn() as conn:
        rows = conn.execute(
            "SELECT * FROM snapshots ORDER BY ts DESC LIMIT ?", (limit,)
        ).fetchall()
    return [_row_to_dict(r) for r in rows]


def get_history_minutes(minutes: int = 60) -> list[dict]:
    cutoff = (datetime.now(timezone.utc) - timedelta(minutes=minutes)).isoformat()
    with _conn() as conn:
        rows = conn.execute(
            "SELECT * FROM snapshots WHERE ts > ? ORDER BY ts ASC", (cutoff,)
        ).fetchall()
    return [_row_to_dict(r) for r in rows]


def solar_fraction_window(minutes: int = 60):
    """
    Solar fraction over a recent trailing window (solar energy / total energy in),
    computed from persisted snapshots so it's stable, meaningful, and survives a
    restart — unlike a counter that resets to a misleading 100% on process start.
    Returns None if there isn't enough data yet.
    """
    cutoff = (datetime.now(timezone.utc) - timedelta(minutes=minutes)).isoformat()
    with _conn() as conn:
        row = conn.execute(
            "SELECT SUM(solar_kw) AS s, SUM(grid_import_kw) AS g "
            "FROM snapshots WHERE ts > ?", (cutoff,)
        ).fetchone()
    solar = row["s"] or 0.0
    grid = row["g"] or 0.0
    total = solar + grid
    if total <= 0:
        return None
    return round(solar / total, 3)


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _row_to_dict(row) -> dict:
    d = dict(row)
    if d.get("zones"):
        d["zones"] = json.loads(d["zones"])
    return d
