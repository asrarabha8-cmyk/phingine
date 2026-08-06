"""
End-to-end smoke test for the whole engine. Run with:
    pytest tests/test_end_to_end.py -v
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
from data.database import Database
from pipeline import run_daily_update
from alerts.alert_engine import check_alerts_for_all_symbols
from ranking.ranking_engine import rank_symbols
from backtesting.backtest_engine import run_backtest
from tests.synthetic_provider import SyntheticProvider


def _fresh_db(tmp_path) -> Database:
    return Database(str(tmp_path / "test_flow.db"))


def test_pipeline_stores_history(tmp_path):
    db = _fresh_db(tmp_path)
    provider = SyntheticProvider(trend="accumulation")

    result = run_daily_update(["TEST_ACC"], provider, db=db)

    assert "TEST_ACC" in result["updated"]
    assert not result["failed"]

    history = db.get_history("TEST_ACC", days=260)
    assert len(history) > 200
    latest = history[-1]
    assert latest["institutional_flow_score"] is not None
    assert 0 <= latest["institutional_flow_score"] <= 100
    assert latest["ema20"] is not None
    assert latest["obv"] is not None


def test_accumulation_symbol_gets_badge_eligible_data(tmp_path):
    db = _fresh_db(tmp_path)
    provider = SyntheticProvider(trend="accumulation")
    run_daily_update(["TEST_ACC2"], provider, db=db)

    from analysis.detection import detect_early_accumulation
    from analysis.flow_trend import classify_flow_trend

    rows = db.get_history("TEST_ACC2", days=30)
    flow_scores = [r["institutional_flow_score"] for r in rows if r["institutional_flow_score"] is not None]
    prices = [r["price"] for r in rows if r["price"] is not None]
    relvols = [r["relative_volume"] for r in rows if r["relative_volume"] is not None]

    trend, slope = classify_flow_trend(flow_scores)
    result = detect_early_accumulation(flow_scores, prices, relvols)

    assert trend is not None
    assert isinstance(result.triggered, bool)


def test_alerts_engine_runs_without_error(tmp_path):
    db = _fresh_db(tmp_path)
    provider = SyntheticProvider(trend="distribution")
    run_daily_update(["TEST_DIST"], provider, db=db)

    alerts = check_alerts_for_all_symbols(db)
    assert isinstance(alerts, list)
    for a in alerts:
        assert a.explanation
        assert a.symbol == "TEST_DIST"


def test_ranking_engine_orders_by_flow_not_price(tmp_path):
    db = _fresh_db(tmp_path)
    run_daily_update(["TEST_A", "TEST_B", "TEST_C"], SyntheticProvider(trend="accumulation"), db=db)

    ranked = rank_symbols(db)
    assert len(ranked) == 3
    scores = [r.flow_score for r in ranked]
    assert scores == sorted(scores, reverse=True)
    assert ranked[0].rank == 1


def test_backtest_runs_and_produces_full_metric_suite(tmp_path):
    db = _fresh_db(tmp_path)
    run_daily_update(["TEST_BT"], SyntheticProvider(trend="accumulation"), db=db)

    report = run_backtest(db, "TEST_BT")
    summary = report.summary()

    for key in ["total_signals", "total_trades", "win_rate_pct", "avg_profit_pct",
                "avg_loss_pct", "max_drawdown_pct", "profit_factor", "sharpe_ratio"]:
        assert key in summary


def test_upsert_is_idempotent(tmp_path):
    """Running the pipeline twice for the same day must not duplicate rows."""
    db = _fresh_db(tmp_path)
    provider = SyntheticProvider(trend="accumulation")
    run_daily_update(["TEST_IDEMPOTENT"], provider, db=db)
    count_1 = len(db.get_history("TEST_IDEMPOTENT", days=10_000))

    run_daily_update(["TEST_IDEMPOTENT"], provider, db=db)
    count_2 = len(db.get_history("TEST_IDEMPOTENT", days=10_000))

    assert count_1 == count_2


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-v"]))
