"""Runs the same checks as test_end_to_end.py using plain asserts, so the
engine can be verified in environments without pytest installed."""
import os
import sys
import tempfile
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from data.database import Database
from pipeline import run_daily_update
from alerts.alert_engine import check_alerts_for_all_symbols
from ranking.ranking_engine import rank_symbols
from backtesting.backtest_engine import run_backtest
from analysis.detection import detect_early_accumulation
from analysis.flow_trend import classify_flow_trend
from tests.synthetic_provider import SyntheticProvider


def fresh_db(tmp_dir, name):
    return Database(os.path.join(tmp_dir, f"{name}.db"))


def run_all(tmp_dir):
    results = []

    def check(name, fn):
        try:
            fn()
            results.append((name, "PASS", None))
        except Exception as e:
            results.append((name, "FAIL", f"{e}\n{traceback.format_exc()}"))

    def t1():
        db = fresh_db(tmp_dir, "t1")
        provider = SyntheticProvider(trend="accumulation")
        result = run_daily_update(["TEST_ACC"], provider, db=db)
        assert "TEST_ACC" in result["updated"], result
        assert not result["failed"], result["failed"]
        history = db.get_history("TEST_ACC", days=260)
        assert len(history) > 200, len(history)
        latest = history[-1]
        assert latest["institutional_flow_score"] is not None
        assert 0 <= latest["institutional_flow_score"] <= 100, latest["institutional_flow_score"]
        assert latest["ema20"] is not None
        assert latest["obv"] is not None

    def t2():
        db = fresh_db(tmp_dir, "t2")
        provider = SyntheticProvider(trend="accumulation")
        run_daily_update(["TEST_ACC2"], provider, db=db)
        rows = db.get_history("TEST_ACC2", days=30)
        flow_scores = [r["institutional_flow_score"] for r in rows if r["institutional_flow_score"] is not None]
        prices = [r["price"] for r in rows if r["price"] is not None]
        relvols = [r["relative_volume"] for r in rows if r["relative_volume"] is not None]
        trend, slope = classify_flow_trend(flow_scores)
        result = detect_early_accumulation(flow_scores, prices, relvols)
        assert trend is not None
        assert isinstance(result.triggered, bool)
        print(f"    -> Flow Trend: {trend.value} (slope={slope}), Early Accumulation triggered={result.triggered}")
        print(f"    -> {result.reason}")

    def t3():
        db = fresh_db(tmp_dir, "t3")
        provider = SyntheticProvider(trend="distribution")
        run_daily_update(["TEST_DIST"], provider, db=db)
        alerts = check_alerts_for_all_symbols(db)
        assert isinstance(alerts, list)
        for a in alerts:
            assert a.explanation
            assert a.symbol == "TEST_DIST"
            print(f"    -> Alert: {a.alert_type} | {a.explanation}")

    def t4():
        db = fresh_db(tmp_dir, "t4")
        run_daily_update(["TEST_A", "TEST_B", "TEST_C"], SyntheticProvider(trend="accumulation"), db=db)
        ranked = rank_symbols(db)
        assert len(ranked) == 3
        scores = [r.flow_score for r in ranked]
        assert scores == sorted(scores, reverse=True)
        assert ranked[0].rank == 1
        for r in ranked:
            print(f"    -> #{r.rank} {r.symbol}: score={r.flow_score}, trend={r.flow_trend.value}")

    def t5():
        db = fresh_db(tmp_dir, "t5")
        run_daily_update(["TEST_BT"], SyntheticProvider(trend="accumulation"), db=db)
        report = run_backtest(db, "TEST_BT")
        summary = report.summary()
        for key in ["total_signals", "total_trades", "win_rate_pct", "avg_profit_pct",
                    "avg_loss_pct", "max_drawdown_pct", "profit_factor", "sharpe_ratio"]:
            assert key in summary
        print(f"    -> Backtest summary: {summary}")

    def t6():
        db = fresh_db(tmp_dir, "t6")
        provider = SyntheticProvider(trend="accumulation")
        run_daily_update(["TEST_IDEMPOTENT"], provider, db=db)
        c1 = len(db.get_history("TEST_IDEMPOTENT", days=10_000))
        run_daily_update(["TEST_IDEMPOTENT"], provider, db=db)
        c2 = len(db.get_history("TEST_IDEMPOTENT", days=10_000))
        assert c1 == c2, (c1, c2)

    check("test_pipeline_stores_history", t1)
    check("test_accumulation_detection_and_trend", t2)
    check("test_alerts_engine_runs", t3)
    check("test_ranking_engine_orders_by_flow", t4)
    check("test_backtest_full_metric_suite", t5)
    check("test_upsert_is_idempotent", t6)

    return results


if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as tmp_dir:
        results = run_all(tmp_dir)

    print("\n" + "=" * 60)
    for name, status, error in results:
        marker = "â" if status == "PASS" else "â"
        print(f"{marker} {name}: {status}")
        if error:
            print(error)
    print("=" * 60)

    failed = [r for r in results if r[1] == "FAIL"]
    sys.exit(1 if failed else 0)
