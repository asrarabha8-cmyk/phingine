"""
Institutional Flow Score: a single 0-100 number that summarizes how much
"smart money" style buying pressure is present, built from the six
indicators already computed in indicators.py.

Each sub-signal is normalized to a 0-100 scale before weighting, so the
weights in config.FlowScoreWeights are directly comparable percentages.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from config import settings


def _normalize_slope(series: pd.Series, window: int = 10) -> pd.Series:
    """
    Convert a raw cumulative series (OBV, A/D) into a 0-100 score based on
    the slope of its recent linear trend, scaled by the series' own recent
    volatility so the score is comparable across stocks of very different size.
    """
    def slope_score(x: np.ndarray) -> float:
        if len(x) < 3 or np.all(x == x[0]):
            return 50.0
        idx = np.arange(len(x))
        slope, _ = np.polyfit(idx, x, 1)
        spread = np.std(x) if np.std(x) > 0 else 1.0
        normalized_slope = slope / spread
        # squash to 0-100 with 50 = flat
        return float(np.clip(50 + normalized_slope * 25, 0, 100))

    return series.rolling(window, min_periods=3).apply(slope_score, raw=True)


def _normalize_bounded(series: pd.Series, low: float, high: float) -> pd.Series:
    """Linearly rescale an already-bounded indicator (e.g. MFI 0-100, CMF -1..1) to 0-100."""
    clipped = series.clip(low, high)
    return ((clipped - low) / (high - low)) * 100


def _normalize_relative_volume(series: pd.Series) -> pd.Series:
    """Relative volume: 1.0x -> 50, 2.0x+ -> 100, 0x -> 0, capped."""
    return (series.clip(0, 2.0) / 2.0) * 100


def _normalize_vwap_position(series: pd.Series) -> pd.Series:
    """VWAP position in % terms; +/-5% treated as the useful range."""
    return _normalize_bounded(series, -5.0, 5.0)


def compute_flow_score(indicators_df: pd.DataFrame) -> pd.Series:
    """
    indicators_df must already contain: obv, cmf, mfi, accumulation_distribution,
    relative_volume, vwap_position (i.e. the output of
    analysis.indicators.compute_all_indicators).
    """
    w = settings.flow_weights

    obv_component = _normalize_slope(indicators_df["obv"])
    ad_component = _normalize_slope(indicators_df["accumulation_distribution"])
    cmf_component = _normalize_bounded(indicators_df["cmf"], -0.3, 0.3)
    mfi_component = indicators_df["mfi"]  # already 0-100
    relvol_component = _normalize_relative_volume(indicators_df["relative_volume"])
    vwap_component = _normalize_vwap_position(indicators_df["vwap_position"])

    score = (
        obv_component * w.obv_slope
        + cmf_component * w.cmf
        + mfi_component * w.mfi
        + ad_component * w.ad_slope
        + relvol_component * w.relative_volume
        + vwap_component * w.vwap_position
    )
    return score.rename("institutional_flow_score").round(2)
