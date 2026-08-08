"""
Daily Historical Update Pipeline.

Run this once per day (cron, GitHub Action, Streamlit scheduled task, etc.)
for every symbol you track. It is the one place that wires together:

    DataProvider -> indicators -> Institutional Flow Score -> Database -> Alerts

Every other module stays decoupled and independently testable.

Symbols are processed in parallel (bounded thread pool) since each symbol's
update is I/O-bound (network call to the data provider) — this cuts wall
clock time roughly proportionally to the worker count, without changing
any of the per-symbol logic.
"""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date

from data.database import Database, FlowRecord, get_database
from data.providers.base import DataProvider, DataProviderError
from analysis.indicators import compute_all_indicators
from analysis.flow_score import compute_flow_score
from alerts.alert_engine import check_alerts, Alert

logger = logging.getLogger("phoenix.pipeline")


def update_symbol(db: Database, provider: DataProvider, symbol: str, lookback_days: int = 260) -> list[Alert]:
    """
    Pulls fresh OHLCV, recomputes every indicator across the lookback window
    (indicators like EMA200/OBV need history to be accurate, not just
    today's bar), writes each session as a row, then evaluates alerts for
    the symbol. Returns any alerts that fired today.
    """
    try:
        ohlcv = provider.get_ohlcv(symbol, lookback_days=lookback_days)
    except DataProviderError as e:
        logger.warning("Skipping %s: %s", symbol, e)
        return []

    if ohlcv.empty:
        logger.warning("No OHLCV data for %s", symbol)
        return []

    enriched = compute_all_indicators(ohlcv)
    enriched["institutional_flow_score"] = compute_flow_score(enriched)

    records = []
    for idx, row in enriched.iterrows():
        records.append(FlowRecord(
            symbol=symbol,
            date=idx.isoformat() if hasattr(idx, "isoformat") else str(idx),
            price=float(row["close"]),
            volume=int(row["volume"]),
            relative_volume=_safe_float(row.get("relative_volume")),
            obv=_safe_float(row.get("obv")),
            cmf=_safe_float(row.get("cmf")),
            mfi=_safe_float(row.get("mfi")),
            accumulation_distribution=_safe_float(row.get("accumulation_distribution")),
            vwap_position=_safe_float(row.get("vwap_position")),
            ema20=_safe_float(row.get("ema20")),
            ema50=_safe_float(row.get("ema50")),
            ema200=_safe_float(row.get("ema200")),
            institutional_flow_score=_safe_float(row.get("institutional_flow_score")),
        ))

    db.upsert_many(records)
    logger.info("Stored %d sessions for %s", len(records), symbol)

    return check_alerts(db, symbol)


def _safe_float(value) -> float | None:
    if value is None:
        return None
    try:
        f = float(value)
        return f if f == f else None  # filter NaN
    except (TypeError, ValueError):
        return None


def run_daily_update(
    symbols: list[str],
    provider: DataProvider,
    db: Database | None = None,
    max_workers: int = 15,
) -> dict:
    """
    Batch entry point. Processes symbols concurrently (I/O-bound network
    calls), so wall clock time scales down roughly with max_workers instead
    of growing linearly with the symbol count. Returns a summary dict:
        {"updated": [...], "failed": [...], "alerts": [Alert, ...]}
    """
    db = db or get_database()
    updated, failed, all_alerts = [], [], []

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(update_symbol, db, provider, symbol): symbol
            for symbol in symbols
        }
        for future in as_completed(futures):
            symbol = futures[future]
            try:
                alerts = future.result()
                updated.append(symbol)
                all_alerts.extend(alerts)
            except Exception as e:
                logger.exception("Failed updating %s", symbol)
                failed.append((symbol, str(e)))

    return {"updated": updated, "failed": failed, "alerts": all_alerts, "run_date": date.today().isoformat()}
