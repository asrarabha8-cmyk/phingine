"""
Central configuration for the Historical Institutional Flow Engine.
Keep every tunable threshold here so behavior can change without touching logic files.
"""
from dataclasses import dataclass, field
import os


@dataclass(frozen=True)
class DatabaseConfig:
    # SQLite today. To move to Postgres later: swap DB_URL and the connection
    # factory in data/database.py — all SQL in this project is ANSI-standard
    # and avoids SQLite-only syntax, so no other file needs to change.
    engine: str = os.getenv("PHOENIX_DB_ENGINE", "sqlite")
    sqlite_path: str = os.getenv("PHOENIX_DB_PATH", "phoenix_flow.db")
    # Used only when engine == "postgres"
    postgres_dsn: str = os.getenv("PHOENIX_PG_DSN", "")


@dataclass(frozen=True)
class FlowScoreWeights:
    """Weights for the Institutional Flow Score (0-100 composite)."""
    obv_slope: float = 0.20
    cmf: float = 0.20
    mfi: float = 0.15
    ad_slope: float = 0.15
    relative_volume: float = 0.15
    vwap_position: float = 0.15
@dataclass(frozen=True)
class ScanFilters:
    min_price: float = 5.0
    min_avg_volume: int = 500_000
    min_market_cap: float = 300_000_000


@dataclass(frozen=True)
class FlowTrendConfig:
    lookback_sessions: int = 5          # sessions used to judge the trend of Flow Score
    strongly_increasing_slope: float = 1.5   # points/session
    increasing_slope: float = 0.4
    weakening_slope: float = -0.4
    strongly_weakening_slope: float = -1.5


@dataclass(frozen=True)
class AccumulationConfig:
    """Early Accumulation: Flow Score rising while price is flat / mildly up."""
    min_flow_score_slope: float = 0.5     # points/session over the lookback
    max_price_change_pct: float = 6.0     # price allowed to drift up to this % (sideways-to-mild-up)
    min_price_change_pct: float = -2.0    # allow small pullbacks, not a real decline
    lookback_sessions: int = 7
    min_relative_volume: float = 1.1      # some volume support required
    prior_quiet_sessions: int = 20        # longer window checked BEFORE the trigger window
    max_prior_price_change_pct: float = 15.0  # price must have been quiet over that longer window too


@dataclass(frozen=True)
class DistributionConfig:
    max_flow_score_slope: float = -0.5    # Flow Score falling
    min_price_change_pct: float = -1.0    # price must actually be weakening
    lookback_sessions: int = 7
    min_relative_volume_on_down_days: float = 1.2


@dataclass(frozen=True)
class AlertConfig:
    surge_points: float = 8.0     # Flow Score rise over `surge_sessions` triggers a bullish alert
    surge_sessions: int = 5
    drop_points: float = -8.0     # Flow Score fall over `drop_sessions` triggers a bearish alert
    drop_sessions: int = 5


@dataclass(frozen=True)
class BacktestConfig:
    entry_signal: str = "early_accumulation"   # or "flow_trend_strongly_increasing"
    holding_period_sessions: int = 10
    stop_loss_pct: float = 8.0
    take_profit_pct: float = 20.0
    risk_free_rate_annual: float = 0.04


@dataclass(frozen=True)
class Settings:
    db: DatabaseConfig = field(default_factory=DatabaseConfig)
    flow_weights: FlowScoreWeights = field(default_factory=FlowScoreWeights)
    flow_trend: FlowTrendConfig = field(default_factory=FlowTrendConfig)
    accumulation: AccumulationConfig = field(default_factory=AccumulationConfig)
    distribution: DistributionConfig = field(default_factory=DistributionConfig)
    alerts: AlertConfig = field(default_factory=AlertConfig)
    backtest: BacktestConfig = field(default_factory=BacktestConfig)


settings = Settings()
