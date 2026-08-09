"""
Ranking Engine: orders symbols by institutional-flow criteria, never by price.

Priority (as specified):
    1. Flow Score
    2. Flow Trend direction
    3. Relative Volume
    4. Trend strength (Flow Score slope magnitude)
    5. Momentum (price rate-of-change)

Accumulation Streak is informational only — it does not affect ranking
order, since a long streak of quiet accumulation can precede a price move
by weeks. It's exposed as a column so the person reviewing results can
distinguish "just starting to accumulate" from "has been accumulating for
a while."

Recent Move % / Already Moved reuse the same "quiet before the signal"
window as analysis.detection.detect_early_accumulation. A Flow Score
ranking alone tends to surface stocks that already had their big breakout
(since volume/momentum indicators react immediately once a move starts),
which is the opposite of catching accumulation early. This flag lets the
UI filter those out without changing the underlying rank order.
"""
from __future__ import annotations

from dataclasses import dataclass

from analysis.flow_trend import FlowTrend, classify_flow_trend, compute_accumulation_streak
from data.database import Database
from config import settings

# Flow Trend has a natural order from best to worst for ranking purposes.
_TREND_RANK = {
    FlowTrend.STRONGLY_INCREASING: 5,
    FlowTrend.INCREASING: 4,
    FlowTrend.STABLE: 3,
    FlowTrend.WEAKENING: 2,
    FlowTrend.STRONGLY_WEAKENING: 1,
    FlowTrend.INSUFFICIENT_DATA: 0,
}


@dataclass(frozen=True)
class RankedSymbol:
    symbol: str
    flow_score: float
    flow_trend: FlowTrend
    flow_trend_slope: float
    relative_volume: float
    trend_strength: float          # abs(slope) — how decisive the trend is
    momentum_pct: float            # price rate of change over the trend lookback
    accumulation_streak: int = 0   # consecutive sessions of non-decreasing Flow Score
    recent_move_pct: float = 0.0   # price change over the longer prior-quiet window
    already_moved: bool = False    # True if that move exceeds the "quiet" threshold
    rank: int = 0


def _momentum_pct(prices: list[float]) -> float:
    if len(prices) < 2 or not prices[0]:
        return 0.0
    return ((prices[-1] - prices[0]) / prices[0]) * 100


def rank_symbols(db: Database, trend_lookback: int = 10) -> list[RankedSymbol]:
    cfg = settings.accumulation
    fetch_window = max(trend_lookback, cfg.prior_quiet_sessions)
    all_rows = db.get_recent_history_bulk(fetch_window)

    by_symbol: dict[str, list] = {}
    for row in all_rows:
        by_symbol.setdefault(row["symbol"], []).append(row)

    scored: list[RankedSymbol] = []

    for symbol, rows in by_symbol.items():
        # rows come back ordered symbol, date ASC — oldest first
        trend_rows = rows[-trend_lookback:]
        flow_scores = [r["institutional_flow_score"] for r in trend_rows if r["institutional_flow_score"] is not None]
        trend_prices = [r["price"] for r in trend_rows if r["price"] is not None]
        if not flow_scores:
            continue

        trend, slope = classify_flow_trend(flow_scores)
        streak = compute_accumulation_streak(flow_scores)
        latest = rows[-1]

        all_prices = [r["price"] for r in rows if r["price"] is not None]
        recent_move_pct = _momentum_pct(all_prices)
        already_moved = abs(recent_move_pct) > cfg.max_prior_price_change_pct

        scored.append(RankedSymbol(
            symbol=symbol,
            flow_score=latest["institutional_flow_score"] or 0.0,
            flow_trend=trend,
            flow_trend_slope=slope,
            relative_volume=latest["relative_volume"] or 0.0,
            trend_strength=abs(slope),
            momentum_pct=_momentum_pct(trend_prices),
            accumulation_streak=streak,
            recent_move_pct=round(recent_move_pct, 2),
            already_moved=already_moved,
        ))

    scored.sort(
        key=lambda s: (
            s.flow_score,
            _TREND_RANK[s.flow_trend],
            s.relative_volume,
            s.trend_strength,
            s.momentum_pct,
        ),
        reverse=True,
    )

    return [
        RankedSymbol(**{**vars(s), "rank": i + 1})
        for i, s in enumerate(scored)
    ]
