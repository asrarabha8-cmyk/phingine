"""
Historical storage layer for the Institutional Flow Engine.

Design notes for the future SQLite -> PostgreSQL migration:
- All SQL below is written in ANSI-compatible form (no SQLite-only functions
  like STRFTIME in the schema itself; date handling stays in Python).
- Access goes through the Database class only. No other module opens a
  connection directly. To migrate: implement a PostgresDatabase with the same
  public methods (get_connection, execute, executemany, fetch_all, fetch_one)
  and swap it in via `get_database()`. Nothing in analysis/, alerts/,
  ranking/, or backtesting/ needs to change.
- Primary key is (symbol, date) so re-running an update for the same day is
  an upsert, not a duplicate row.
"""
from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager
from dataclasses import dataclass, asdict
from datetime import date, datetime
from typing import Optional, Iterable

from config import settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS flow_history (
    symbol              TEXT    NOT NULL,
    date                TEXT    NOT NULL,   -- ISO format YYYY-MM-DD
    price               REAL    NOT NULL,
    volume              INTEGER NOT NULL,
    relative_volume     REAL,
    obv                 REAL,
    cmf                 REAL,
    mfi                 REAL,
    accumulation_distribution REAL,
    vwap_position       REAL,               -- e.g. % distance of price from session VWAP
    ema20               REAL,
    ema50               REAL,
    ema200              REAL,
    institutional_flow_score REAL,
    created_at          TEXT    NOT NULL,
    PRIMARY KEY (symbol, date)
);

CREATE INDEX IF NOT EXISTS idx_flow_history_symbol_date
    ON flow_history (symbol, date);

CREATE TABLE IF NOT EXISTS alerts (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol          TEXT    NOT NULL,
    date            TEXT    NOT NULL,
    alert_type      TEXT    NOT NULL,   -- 'flow_surge' | 'flow_drop' | 'early_accumulation' | 'distribution'
    flow_score      REAL,
    flow_score_change REAL,
    explanation     TEXT    NOT NULL,
    created_at      TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_alerts_symbol_date
    ON alerts (symbol, date);
"""


@dataclass
class FlowRecord:
    symbol: str
    date: str                       # ISO date string
    price: float
    volume: int
    relative_volume: Optional[float] = None
    obv: Optional[float] = None
    cmf: Optional[float] = None
    mfi: Optional[float] = None
    accumulation_distribution: Optional[float] = None
    vwap_position: Optional[float] = None
    ema20: Optional[float] = None
    ema50: Optional[float] = None
    ema200: Optional[float] = None
    institutional_flow_score: Optional[float] = None


class Database:
    """Thin, thread-safe wrapper. Swap this class for a Postgres
    implementation later without touching any calling code."""

    def __init__(self, path: str):
        self._path = path
        self._local = threading.local()
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        if not hasattr(self._local, "conn"):
            conn = sqlite3.connect(self._path, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys = ON")
            self._local.conn = conn
        return self._local.conn

    def _init_schema(self):
        conn = self._connect()
        conn.executescript(SCHEMA)
        conn.commit()

    @contextmanager
    def cursor(self):
        conn = self._connect()
        cur = conn.cursor()
        try:
            yield cur
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            cur.close()

    # ---------- Flow history ----------

    def upsert_flow_record(self, record: FlowRecord) -> None:
        data = asdict(record)
        data["created_at"] = datetime.utcnow().isoformat()
        columns = ", ".join(data.keys())
        placeholders = ", ".join(f":{k}" for k in data.keys())
        update_clause = ", ".join(
            f"{k}=excluded.{k}" for k in data.keys() if k not in ("symbol", "date")
        )
        sql = f"""
            INSERT INTO flow_history ({columns}) VALUES ({placeholders})
            ON CONFLICT(symbol, date) DO UPDATE SET {update_clause}
        """
        with self.cursor() as cur:
            cur.execute(sql, data)

    def upsert_many(self, records: Iterable[FlowRecord]) -> None:
        for r in records:
            self.upsert_flow_record(r)

    def get_history(self, symbol: str, days: int) -> list[sqlite3.Row]:
        """Most recent `days` sessions for a symbol, oldest first."""
        with self.cursor() as cur:
            cur.execute(
                """
                SELECT * FROM (
                    SELECT * FROM flow_history
                    WHERE symbol = :symbol
                    ORDER BY date DESC
                    LIMIT :days
                ) sub
                ORDER BY date ASC
                """,
                {"symbol": symbol, "days": days},
            )
            return cur.fetchall()

    def get_latest(self, symbol: str) -> Optional[sqlite3.Row]:
        with self.cursor() as cur:
            cur.execute(
                "SELECT * FROM flow_history WHERE symbol = :symbol ORDER BY date DESC LIMIT 1",
                {"symbol": symbol},
            )
            return cur.fetchone()

    def get_all_symbols(self) -> list[str]:
        with self.cursor() as cur:
            cur.execute("SELECT DISTINCT symbol FROM flow_history")
            return [row["symbol"] for row in cur.fetchall()]

    def get_latest_for_all_symbols(self) -> list[sqlite3.Row]:
        """One row per symbol: its most recent session. Used by the ranking engine."""
        with self.cursor() as cur:
            cur.execute(
                """
                SELECT fh.* FROM flow_history fh
                INNER JOIN (
                    SELECT symbol, MAX(date) AS max_date
                    FROM flow_history GROUP BY symbol
                ) latest
                ON fh.symbol = latest.symbol AND fh.date = latest.max_date
                """
            )
            return cur.fetchall()

    # ---------- Alerts ----------

    def insert_alert(self, symbol: str, date_: str, alert_type: str,
                      flow_score: float, flow_score_change: float, explanation: str) -> None:
        with self.cursor() as cur:
            cur.execute(
                """
                INSERT INTO alerts (symbol, date, alert_type, flow_score, flow_score_change, explanation, created_at)
                VALUES (:symbol, :date, :alert_type, :flow_score, :flow_score_change, :explanation, :created_at)
                """,
                {
                    "symbol": symbol, "date": date_, "alert_type": alert_type,
                    "flow_score": flow_score, "flow_score_change": flow_score_change,
                    "explanation": explanation, "created_at": datetime.utcnow().isoformat(),
                },
            )

    def get_recent_alerts(self, limit: int = 100) -> list[sqlite3.Row]:
        with self.cursor() as cur:
            cur.execute(
                "SELECT * FROM alerts ORDER BY created_at DESC LIMIT :limit",
                {"limit": limit},
            )
            return cur.fetchall()

    def alert_already_fired(self, symbol: str, date_: str, alert_type: str) -> bool:
        with self.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM alerts WHERE symbol=:s AND date=:d AND alert_type=:t LIMIT 1",
                {"s": symbol, "d": date_, "t": alert_type},
            )
            return cur.fetchone() is not None


_db_instance: Optional[Database] = None


def get_database() -> Database:
    """Singleton accessor. When migrating to Postgres, change this function
    to return a PostgresDatabase instance based on settings.db.engine â
    every caller in the project uses get_database() and needs no edits."""
    global _db_instance
    if _db_instance is None:
        if settings.db.engine == "sqlite":
            _db_instance = Database(settings.db.sqlite_path)
        else:
            raise NotImplementedError(
                "Postgres engine not implemented yet. Implement a PostgresDatabase "
                "class with the same public interface as Database and return it here."
            )
    return _db_instance
