"""
Backtesting Engine.

Replays history stored in flow_history: for every session where the Early
Accumulation condition would have triggered, simulates a trade using the
configured holding period / stop-loss / take-profit, then reports the full
metric suite (win rate, profit factor, Sharpe ratio, max drawdown, ...).

This is a signal backtest, not a full portfolio simulator — one position at
a time per symbol, no position sizing beyond 1 unit. That's an intentional
scope boundary: extending it to portfolio-level simulation (capital
allocation, concurrent positions, slippage model) is a separate, larger
piece of work and should be a follow-up module, not bolted on here.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from config import settings
from data.database import Database
from analysis.detection import detect_early_accumulation


@dataclass
class Trade:
    symbol: str
    entry_date: str
    entry_price: float
    exit_date: str
    exit_price: float
    exit_reason: str   # 'take_profit' | 'stop_loss' | 'time_exit'
    return_pct: float


@dataclass
class BacktestReport:
    total_signals: int
    trades: list[Trade] = field(default_factory=list)

    @property
    def win_rate(self) -> float:
        if not self.trades:
            return 0.0
        wins = sum(1 for t in self.trades if t.return_pct > 0)
        return round(wins / len(self.trades) * 100, 2)

    @property
    def avg_profit_pct(self) -> float:
        wins = [t.return_pct for t in self.trades if t.return_pct > 0]
        return round(float(np.mean(wins)), 2) if wins else 0.0

    @property
    def avg_loss_pct(self) -> float:
        losses = [t.return_pct for t in self.trades if t.return_pct <= 0]
        return round(float(np.mean(losses)), 2) if losses else 0.0

    @property
    def max_drawdown_pct(self) -> float:
        if not self.trades:
            return 0.0
        equity = np.cumprod([1 + t.return_pct / 100 for t in self.trades])
        running_max = np.maximum.accumulate(equity)
        drawdown = (equity - running_max) / running_max
        return round(float(drawdown.min()) * 100, 2)

    @property
    def profit_factor(self) -> float:
        gross_profit = sum(t.return_pct for t in self.trades if t.return_pct > 0)
        gross_loss = abs(sum(t.return_pct for t in self.trades if t.return_pct <= 0))
        if gross_loss == 0:
            return float("inf") if gross_profit > 0 else 0.0
        return round(gross_profit / gross_loss, 2)

    @property
    def sharpe_ratio(self) -> float:
        """Annualized, assuming each trade's return is one 'period' and using
        the configured holding period to approximate periods per year."""
        if len(self.trades) < 2:
            return 0.0
        returns = np.array([t.return_pct / 100 for t in self.trades])
        periods_per_year = 252 / max(settings.backtest.holding_period_sessions, 1)
        excess = returns - (settings.backtest.risk_free_rate_annual / periods_per_year)
        if excess.std() == 0:
            return 0.0
        return round(float(np.mean(excess) / np.std(excess) * np.sqrt(periods_per_year)), 2)

    def summary(self) -> dict:
        return {
            "total_signals": self.total_signals,
            "total_trades": len(self.trades),
            "win_rate_pct": self.win_rate,
            "avg_profit_pct": self.avg_profit_pct,
            "avg_loss_pct": self.avg_loss_pct,
            "max_drawdown_pct": self.max_drawdown_pct,
            "profit_factor": self.profit_factor,
            "sharpe_ratio": self.sharpe_ratio,
        }


def _simulate_trade(rows: list, entry_idx: int) -> Trade | None:
    cfg = settings.backtest
    entry_row = rows[entry_idx]
    entry_price = entry_row["price"]
    if not entry_price:
        return None

    exit_end = min(entry_idx + cfg.holding_period_sessions, len(rows) - 1)
    for i in range(entry_idx + 1, exit_end + 1):
        price = rows[i]["price"]
        if not price:
            continue
        change_pct = (price - entry_price) / entry_price * 100
        if change_pct >= cfg.take_profit_pct:
            return Trade(entry_row["symbol"], entry_row["date"], entry_price,
                         rows[i]["date"], price, "take_profit", round(change_pct, 2))
        if change_pct <= -cfg.stop_loss_pct:
            return Trade(entry_row["symbol"], entry_row["date"], entry_price,
                         rows[i]["date"], price, "stop_loss", round(change_pct, 2))

    # time exit at the end of the holding period
    exit_row = rows[exit_end]
    if not exit_row["price"]:
        return None
    change_pct = (exit_row["price"] - entry_price) / entry_price * 100
    return Trade(entry_row["symbol"], entry_row["date"], entry_price,
                 exit_row["date"], exit_row["price"], "time_exit", round(change_pct, 2))


def run_backtest(db: Database, symbol: str | None = None) -> BacktestReport:
    """
    If symbol is None, backtests every symbol in the database and pools
    the trades into one report.
    """
    cfg_lookback = settings.accumulation.lookback_sessions
    symbols = [symbol] if symbol else db.get_all_symbols()

    trades: list[Trade] = []
    total_signals = 0

    for sym in symbols:
        rows = db.get_history(sym, days=10_000)  # full history
        if len(rows) < cfg_lookback + 1:
            continue

        for i in range(cfg_lookback, len(rows)):
            window = rows[max(0, i - cfg_lookback + 1): i + 1]
            flow_scores = [r["institutional_flow_score"] for r in window if r["institutional_flow_score"] is not None]
            prices = [r["price"] for r in window if r["price"] is not None]
            relvols = [r["relative_volume"] for r in window if r["relative_volume"] is not None]

            if len(flow_scores) < cfg_lookback or len(prices) < cfg_lookback:
                continue

            result = detect_early_accumulation(flow_scores, prices, relvols)
            if result.triggered:
                total_signals += 1
                trade = _simulate_trade(rows, i)
                if trade:
                    trades.append(trade)

    return BacktestReport(total_signals=total_signals, trades=trades)
