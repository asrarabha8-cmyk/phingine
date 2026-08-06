"""
Pure indicator calculations. Every function takes a DataFrame with columns
['open', 'high', 'low', 'close', 'volume'] indexed by date (ascending) and
returns a pandas Series aligned to that same index. No I/O, no side effects —
this makes every function trivially unit-testable.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def obv(df: pd.DataFrame) -> pd.Series:
    """On-Balance Volume: cumulative volume, signed by the direction of the close."""
    direction = np.sign(df["close"].diff()).fillna(0)
    return (direction * df["volume"]).cumsum().rename("obv")


def relative_volume(df: pd.DataFrame, lookback: int = 20) -> pd.Series:
    """Today's volume vs the rolling average volume (excluding today)."""
    avg_vol = df["volume"].shift(1).rolling(lookback, min_periods=5).mean()
    return (df["volume"] / avg_vol).rename("relative_volume")


def money_flow_multiplier(df: pd.DataFrame) -> pd.Series:
    high_low_range = (df["high"] - df["low"]).replace(0, np.nan)
    mfm = ((df["close"] - df["low"]) - (df["high"] - df["close"])) / high_low_range
    return mfm.fillna(0.0)


def accumulation_distribution(df: pd.DataFrame) -> pd.Series:
    """Cumulative Accumulation/Distribution line."""
    mfm = money_flow_multiplier(df)
    mfv = mfm * df["volume"]
    return mfv.cumsum().rename("accumulation_distribution")


def cmf(df: pd.DataFrame, period: int = 20) -> pd.Series:
    """Chaikin Money Flow: sum(MFV) / sum(volume) over the period."""
    mfm = money_flow_multiplier(df)
    mfv = mfm * df["volume"]
    result = mfv.rolling(period).sum() / df["volume"].rolling(period).sum()
    return result.rename("cmf")


def mfi(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Money Flow Index (volume-weighted RSI), 0-100."""
    typical_price = (df["high"] + df["low"] + df["close"]) / 3
    raw_money_flow = typical_price * df["volume"]

    price_change = typical_price.diff()
    positive_flow = raw_money_flow.where(price_change > 0, 0.0)
    negative_flow = raw_money_flow.where(price_change < 0, 0.0)

    pos_sum = positive_flow.rolling(period).sum()
    neg_sum = negative_flow.rolling(period).sum().replace(0, np.nan)

    money_ratio = pos_sum / neg_sum
    result = 100 - (100 / (1 + money_ratio))
    return result.fillna(50.0).rename("mfi")  # neutral 50 when undefined (no negative flow)


def vwap_position(df: pd.DataFrame, period: int = 20) -> pd.Series:
    """
    % distance of close from a rolling VWAP (proxy for session VWAP when only
    daily bars are available). Positive = trading above VWAP.
    """
    typical_price = (df["high"] + df["low"] + df["close"]) / 3
    pv = typical_price * df["volume"]
    rolling_vwap = pv.rolling(period).sum() / df["volume"].rolling(period).sum()
    return (((df["close"] - rolling_vwap) / rolling_vwap) * 100).rename("vwap_position")


def ema(df: pd.DataFrame, period: int) -> pd.Series:
    return df["close"].ewm(span=period, adjust=False).mean().rename(f"ema{period}")


def compute_all_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Convenience: attach every indicator as a column on a copy of df."""
    out = df.copy()
    out["obv"] = obv(df)
    out["relative_volume"] = relative_volume(df)
    out["cmf"] = cmf(df)
    out["mfi"] = mfi(df)
    out["accumulation_distribution"] = accumulation_distribution(df)
    out["vwap_position"] = vwap_position(df)
    out["ema20"] = ema(df, 20)
    out["ema50"] = ema(df, 50)
    out["ema200"] = ema(df, 200)
    return out
