"""
Early Accumulation Detection and Institutional Distribution Detection.

Both look at the relationship between price behavior and Flow Score
behavior over a multi-session window — never a single day.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from config import settings


@dataclass(frozen=True)
class DetectionResult:
    triggered: bool
    flow_score_slope: float
    price_change_pct: float
    avg_relative_volume: float
    reason: str


def _slope(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    idx = np.arange(len(values))
    slope, _ = np.polyfit(idx, np.array(values, dtype=float), 1)
    return float(slope)


def detect_early_accumulation(
    flow_scores: list[float],
    prices: list[float],
    relative_volumes: list[float],
) -> DetectionResult:
    """
    Badge: "Early Institutional Accumulation"
    Condition: Flow Score rising steadily while price is sideways or only
    mildly higher (i.e. buying pressure is building before the market has
    repriced the stock), with some real volume behind it — AND the price
    must have already been quiet over a longer prior window, not just the
    trigger window itself. Without this, a stock that just started an
    explosive breakout can satisfy the short-window "sideways" check on
    its very first breakout day (since Flow Score reacts to volume/price
    immediately), firing the signal right as the move begins rather than
    before it — which is the opposite of the intent.
    """
    cfg = settings.accumulation
    n = cfg.lookback_sessions
    if len(flow_scores) < n or len(prices) < n:
        return DetectionResult(False, 0.0, 0.0, 0.0, "Not enough history")

    fs_window = flow_scores[-n:]
    price_window = prices[-n:]
    relvol_window = relative_volumes[-n:] if relative_volumes else []

    fs_slope = _slope(fs_window)
    price_change_pct = ((price_window[-1] - price_window[0]) / price_window[0]) * 100 if price_window[0] else 0.0
    avg_relvol = float(np.mean(relvol_window)) if relvol_window else 0.0

    conditions = {
        "flow_score_rising": fs_slope >= cfg.min_flow_score_slope,
        "price_sideways_or_mild_up": cfg.min_price_change_pct <= price_change_pct <= cfg.max_price_change_pct,
        "volume_support": avg_relvol >= cfg.min_relative_volume,
    }

    # Longer prior window check: price shouldn't have already made a big
    # move before the trigger window either — otherwise we're catching a
    # breakout in progress, not genuine early accumulation.
    prior_n = cfg.prior_quiet_sessions
    if len(prices) >= prior_n:
        prior_window = prices[-prior_n:-n] if len(prices) >= prior_n + n else prices[:-n]
        if len(prior_window) >= 2 and prior_window[0]:
            prior_change_pct = ((prior_window[-1] - prior_window[0]) / prior_window[0]) * 100
            conditions["quiet_before_trigger"] = abs(prior_change_pct) <= cfg.max_prior_price_change_pct
        else:
            conditions["quiet_before_trigger"] = True
    else:
        conditions["quiet_before_trigger"] = True

    triggered = all(conditions.values())

    if triggered:
        reason = (
            f"Flow Score rose at {fs_slope:.2f} pts/session over the last {n} sessions "
            f"while price moved only {price_change_pct:+.1f}%, with average relative volume "
            f"of {avg_relvol:.2f}x — buying pressure is building ahead of a price move."
        )
    else:
        failed = [k for k, v in conditions.items() if not v]
        reason = f"Conditions not met: {', '.join(failed)}"

    return DetectionResult(triggered, round(fs_slope, 3), round(price_change_pct, 2), round(avg_relvol, 2), reason)



def detect_distribution(
    flow_scores: list[float],
    prices: list[float],
    relative_volumes: list[float],
) -> DetectionResult:
    """
    Badge: "Institutional Distribution"
    Condition: Flow Score falling while price is weakening, with elevated
    volume on the down days — smart money exiting into strength/liquidity.
    """
    cfg = settings.distribution
    n = cfg.lookback_sessions
    if len(flow_scores) < n or len(prices) < n:
        return DetectionResult(False, 0.0, 0.0, 0.0, "Not enough history")

    fs_window = flow_scores[-n:]
    price_window = prices[-n:]
    relvol_window = relative_volumes[-n:] if relative_volumes else []

    fs_slope = _slope(fs_window)
    price_change_pct = ((price_window[-1] - price_window[0]) / price_window[0]) * 100 if price_window[0] else 0.0

    # average relative volume specifically on the down days in the window
    down_day_volumes = [
        relvol_window[i] for i in range(1, len(price_window))
        if price_window[i] < price_window[i - 1] and i < len(relvol_window)
    ]
    avg_down_relvol = float(np.mean(down_day_volumes)) if down_day_volumes else 0.0

    conditions = {
        "flow_score_falling": fs_slope <= cfg.max_flow_score_slope,
        "price_weakening": price_change_pct <= cfg.min_price_change_pct,
        "selling_volume_elevated": avg_down_relvol >= cfg.min_relative_volume_on_down_days,
    }
    triggered = all(conditions.values())

    if triggered:
        reason = (
            f"Flow Score fell at {fs_slope:.2f} pts/session over the last {n} sessions "
            f"while price declined {price_change_pct:+.1f}%, with average relative volume of "
            f"{avg_down_relvol:.2f}x on down days — signs of institutional selling."
        )
    else:
        failed = [k for k, v in conditions.items() if not v]
        reason = f"Conditions not met: {', '.join(failed)}"

    return DetectionResult(triggered, round(fs_slope, 3), round(price_change_pct, 2), round(avg_down_relvol, 2), reason)
