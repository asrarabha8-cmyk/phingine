"""
Smart Alerts: watches multi-session Flow Score changes and raises alerts
when they cross configured thresholds. Every alert is persisted with a
natural-language explanation (see explainer.py) so the user never sees a
bare number without context.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from config import settings
from data.database import Database
from alerts.explainer import explain_alert


@dataclass(frozen=True)
class Alert:
    symbol: str
    date: str
    alert_type: str          # 'flow_surge' | 'flow_drop'
    flow_score: float
    flow_score_change: float
    explanation: str


def check_alerts(db: Database, symbol: str) -> list[Alert]:
    """
    Call once per symbol after its daily flow_history row has been written.
    Looks back over the configured session windows and raises whichever
    alerts qualify, skipping any that already fired for this symbol/date.
    """
    cfg = settings.alerts
    lookback = max(cfg.surge_sessions, cfg.drop_sessions) + 1
    rows = db.get_history(symbol, lookback)
    if len(rows) < 2:
        return []

    latest = rows[-1]
    today = latest["date"]
    fired: list[Alert] = []

    # Surge check
    surge_window = rows[-cfg.surge_sessions:] if len(rows) >= cfg.surge_sessions else rows
    surge_change = (surge_window[-1]["institutional_flow_score"] or 0) - (surge_window[0]["institutional_flow_score"] or 0)
    if surge_change >= cfg.surge_points and not db.alert_already_fired(symbol, today, "flow_surge"):
        explanation = explain_alert(
            symbol=symbol, alert_type="flow_surge", change=surge_change,
            sessions=len(surge_window), rows=surge_window,
        )
        db.insert_alert(symbol, today, "flow_surge", latest["institutional_flow_score"], surge_change, explanation)
        fired.append(Alert(symbol, today, "flow_surge", latest["institutional_flow_score"], surge_change, explanation))

    # Drop check
    drop_window = rows[-cfg.drop_sessions:] if len(rows) >= cfg.drop_sessions else rows
    drop_change = (drop_window[-1]["institutional_flow_score"] or 0) - (drop_window[0]["institutional_flow_score"] or 0)
    if drop_change <= cfg.drop_points and not db.alert_already_fired(symbol, today, "flow_drop"):
        explanation = explain_alert(
            symbol=symbol, alert_type="flow_drop", change=drop_change,
            sessions=len(drop_window), rows=drop_window,
        )
        db.insert_alert(symbol, today, "flow_drop", latest["institutional_flow_score"], drop_change, explanation)
        fired.append(Alert(symbol, today, "flow_drop", latest["institutional_flow_score"], drop_change, explanation))

    return fired


def check_alerts_for_all_symbols(db: Database) -> list[Alert]:
    all_alerts: list[Alert] = []
    for symbol in db.get_all_symbols():
        all_alerts.extend(check_alerts(db, symbol))
    return all_alerts
