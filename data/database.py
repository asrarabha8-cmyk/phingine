"""
Historical storage layer for the Institutional Flow Engine.

Supports SQLite (default, ephemeral on Streamlit Cloud) and PostgreSQL
(persistent, recommended for production). Both implementations expose the
exact same public interface, so nothing in analysis/, alerts/, ranking/,
or backtesting/ needs to change regardless of which engine is active.

To use Postgres: set a DATABASE_URL secret (Streamlit secrets or
environment variable) with a standard postgresql:// connection string.
If DATABASE_URL is not set, the app falls back to local SQLite.
"""
from __future__ import annotations

import os
import sqlite3
import threading
from contextlib import contextmanager
from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Optional, Iterable

from config import settings

SQLITE_SCHEMA = """
CREATE TABLE IF NOT EXISTS flow_history (
    symbol              TEXT    NOT NULL,
    date                TEXT    NOT NULL,
    price               REAL    NOT NULL,
    volume              INTEGER NOT NULL,
    relative_volume     REAL,
    obv                 REAL,
    cmf                 REAL,
    mfi                 REAL,
    accumulation_distribution REAL,
    vwap_position       REAL,
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
    alert_type      TEXT    NOT NULL,
    flow_score      REAL,
    flow_score_change REAL,
    explanation     TEXT    NOT NULL,
    created_at      TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_alerts_symbol_date
    ON alerts (symbol, date);
"""

POSTGRES_SCHEMA = """
CREATE TABLE IF NOT EXISTS flow_history (
    symbol              TEXT    NOT NULL,
    date                TEXT    NOT NULL,
    price               DOUBLE PRECISION NOT NULL,
    volume              BIGINT  NOT NULL,
    relative_volume     DOUBLE PRECISION,
    obv                 DOUBLE PRECISION,
    cmf                 DOUBLE PRECISION,
    mfi                 DOUBLE PRECISION,
    accumulation_distribution DOUBLE PRECISION,
    vwap_position       DOUBLE PRECISION,
    ema20               DOUBLE PRECISION,
    ema50               DOUBLE PRECISION,
    ema200              DOUBLE PRECISION,
    institutional_flow_score DOUBLE PRECISION,
    created_at          TEXT    NOT NULL,
    PRIMARY KEY (symbol, date)
);

CREATE INDEX IF NOT EXISTS idx_flow_history_symbol_date
    ON flow_history (symbol, date);

CREATE TABLE IF NOT EXISTS alerts (
    id              SERIAL PRIMARY KEY,
    symbol          TEXT    NOT NULL,
    date            TEXT    NOT NULL,
    alert_type      TEXT    NOT NULL,
    flow_score      DOUBLE PRECISION,
    flow_score_change DOUBLE PRECISION,
    explanation     TEXT    NOT NULL,
    created_at      TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_alerts_symbol_date
    ON alerts (symbol, date);
"""


@dataclass
class FlowRecord:
    symbol: str
    date: str
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
    """SQLite implementation. Ephemeral on Streamlit Cloud — data is lost
    on every redeploy. Kept as the offline/local-dev fallback."""

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
        conn.executescript(SQLITE_SCHEMA)
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

    def get_history(self, symbol: str, days: int) -> list:
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

    def get_latest(self, symbol: str):
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

    def get_latest_for_all_symbols(self) -> list:
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

    def get_recent_alerts(self, limit: int = 100) -> list:
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


class PostgresDatabase:
    """PostgreSQL implementation (e.g. Supabase). Persistent across
    Streamlit Cloud redeploys — this is the recommended engine for
    production use. Same public interface as Database."""

    def __init__(self, dsn: str):
        import psycopg2
        import psycopg2.extras
        self._psycopg2 = psycopg2
        self._extras = psycopg2.extras
        self._dsn = dsn
        self._local = threading.local()
        self._init_schema()

    def _connect(self):
        if not hasattr(self._local, "conn") or self._local.conn.closed:
            conn = self._psycopg2.connect(self._dsn)
            conn.autocommit = False
            self._local.conn = conn
        return self._local.conn

    def _init_schema(self):
        conn = self._connect()
        with conn.cursor() as cur:
            cur.execute(POSTGRES_SCHEMA)
        conn.commit()

    @contextmanager
    def cursor(self):
        conn = self._connect()
        cur = conn.cursor(cursor_factory=self._extras.RealDictCursor)
        try:
            yield cur
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            cur.close()

    def upsert_flow_record(self, record: FlowRecord) -> None:
        data = asdict(record)
        data["created_at"] = datetime.utcnow().isoformat()
        columns = ", ".join(data.keys())
        placeholders = ", ".join(f"%({k})s" for k in data.keys())
        update_clause = ", ".join(
            f"{k}=EXCLUDED.{k}" for k in data.keys() if k not in ("symbol", "date")
        )
        sql = f"""
            INSERT INTO flow_history ({columns}) VALUES ({placeholders})
            ON CONFLICT (symbol, date) DO UPDATE SET {update_clause}
        """
        with self.cursor() as cur:
            cur.execute(sql, data)

    def upsert_many(self, records: Iterable[FlowRecord]) -> None:
        for r in records:
            self.upsert_flow_record(r)

    def get_history(self, symbol: str, days: int) -> list:
        with self.cursor() as cur:
            cur.execute(
                """
                SELECT * FROM (
                    SELECT * FROM flow_history
                    WHERE symbol = %(symbol)s
                    ORDER BY date DESC
                    LIMIT %(days)s
                ) sub
                ORDER BY date ASC
                """,
                {"symbol": symbol, "days": days},
            )
            return cur.fetchall()

    def get_latest(self, symbol: str):
        with self.cursor() as cur:
            cur.execute(
                "SELECT * FROM flow_history WHERE symbol = %(symbol)s ORDER BY date DESC LIMIT 1",
                {"symbol": symbol},
            )
            return cur.fetchone()

    def get_all_symbols(self) -> list[str]:
        with self.cursor() as cur:
            cur.execute("SELECT DISTINCT symbol FROM flow_history")
            return [row["symbol"] for row in cur.fetchall()]

    def get_latest_for_all_symbols(self) -> list:
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

    def insert_alert(self, symbol: str, date_: str, alert_type: str,
                      flow_score: float, flow_score_change: float, explanation: str) -> None:
        with self.cursor() as cur:
            cur.execute(
                """
                INSERT INTO alerts (symbol, date, alert_type, flow_score, flow_score_change, explanation, created_at)
                VALUES (%(symbol)s, %(date)s, %(alert_type)s, %(flow_score)s, %(flow_score_change)s, %(explanation)s, %(created_at)s)
                """,
                {
                    "symbol": symbol, "date": date_, "alert_type": alert_type,
                    "flow_score": flow_score, "flow_score_change": flow_score_change,
                    "explanation": explanation, "created_at": datetime.utcnow().isoformat(),
                },
            )

    def get_recent_alerts(self, limit: int = 100) -> list:
        with self.cursor() as cur:
            cur.execute(
                "SELECT * FROM alerts ORDER BY created_at DESC LIMIT %(limit)s",
                {"limit": limit},
            )
            return cur.fetchall()

    def alert_already_fired(self, symbol: str, date_: str, alert_type: str) -> bool:
        with self.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM alerts WHERE symbol=%(s)s AND date=%(d)s AND alert_type=%(t)s LIMIT 1",
                {"s": symbol, "d": date_, "t": alert_type},
            )
            return cur.fetchone() is not None


_db_instance = None


def _get_database_url() -> Optional[str]:
    """Checks Streamlit secrets first (if running inside Streamlit),
    then falls back to a plain environment variable."""
    try:
        import streamlit as st
        if "DATABASE_URL" in st.secrets:
            return st.secrets["DATABASE_URL"]
    except Exception:
        pass
    return os.getenv("DATABASE_URL")


def get_database():
    """Singleton accessor. Automatically uses PostgreSQL if a DATABASE_URL
    secret/env var is present; otherwise falls back to local SQLite."""
    global _db_instance
    if _db_instance is None:
        database_url = _get_database_url()
        if database_url:
            _db_instance = PostgresDatabase(database_url)
        elif settings.db.engine == "sqlite":
            _db_instance = Database(settings.db.sqlite_path)
        else:
            raise NotImplementedError(
                "No DATABASE_URL set and engine is not sqlite."
            )
    return _db_instance
