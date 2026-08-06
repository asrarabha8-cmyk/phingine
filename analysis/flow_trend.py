"""
Flow Trend: classifies the *direction* of the Institutional Flow Score over
several sessions (never from a single day's value).
"""
from __future__ import annotations

from enum import Enum

import numpy as np

from config import settings


class FlowTrend(str, Enum):
    STRONGLY_INCREASING = "Strongly Increasing"
    INCREASING = "Increasing"
    STABLE = "Stable"
    WEAKENING = "Weakening"
    STRONGLY_WEAKENING = "Strongly Weakening"
    INSUFFICIENT_DATA = "Insufficient Data"


def _slope_per_session(flow_scores: list[float]) -> float:
    idx = np.arange(len(flow_scores))
    slope, _ = np.polyfit(idx, np.array(flow_scores, dtype=float), 1)
    return float(slope)


def classify_flow_trend(flow_scores: list[float]) -> tuple[FlowTrend, float]:
    """
    flow_scores: chronological (oldest first) Institutional Flow Score values,
    at least config.flow_trend.lookback_sessions long for a real classification.
    Returns (trend_label, slope_points_per_session).
    """
    cfg = settings.flow_trend
    if len(flow_scores) < min(3, cfg.lookback_sessions):
        return FlowTrend.INSUFFICIENT_DATA, 0.0

    window = flow_scores[-cfg.lookback_sessions:]
    slope = _slope_per_session(window)

    if slope >= cfg.strongly_increasing_slope:
        trend = FlowTrend.STRONGLY_INCREASING
    elif slope >= cfg.increasing_slope:
        trend = FlowTrend.INCREASING
    elif slope <= cfg.strongly_weakening_slope:
        trend = FlowTrend.STRONGLY_WEAKENING
    elif slope <= cfg.weakening_slope:
        trend = FlowTrend.WEAKENING
    else:
        trend = FlowTrend.STABLE

    return trend, round(slope, 3)