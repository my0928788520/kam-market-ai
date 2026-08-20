from datetime import UTC, datetime, timedelta
from decimal import Decimal

from kam_market_ai.paper_trading.paper_wave_stop_comparison import (
    PaperWaveStopComparisonTracker,
)


def test_short_fixed_stop_can_be_saved_by_buffered_equal_wave_stop(tmp_path) -> None:
    path = tmp_path / "wave-comparison.json"
    tracker = PaperWaveStopComparisonTracker(path)
    started = datetime(2026, 8, 20, 1, tzinfo=UTC)
    tracker.start(
        trade_id="trade-1",
        side="SELL",
        entry_price=Decimal(44911),
        fixed_stop_price=Decimal(44931),
        observed_at=started,
    )
    tracker.observe(
        trade_id="trade-1",
        price=Decimal(44935),
        observed_at=started + timedelta(seconds=3),
        wave_pivot_price=Decimal(44940),
        buffer_points=Decimal(20),
    )
    tracker.observe(
        trade_id="trade-1",
        price=Decimal(44840),
        observed_at=started + timedelta(seconds=6),
        wave_pivot_price=Decimal(44940),
        buffer_points=Decimal(20),
    )
    tracker.finish(
        observed_at=started + timedelta(seconds=9),
        actual_exit_price=Decimal(44840),
    )

    summary = PaperWaveStopComparisonTracker(path).safe_payload()
    assert summary["sample_size"] == 1
    assert summary["fixed_stop_exits"] == 1
    assert summary["wave_stop_exits"] == 0
    assert summary["saved_by_wave_stop"] == 1
    assert summary["verdict"] == "樣本不足"
    assert summary["dry_run"] is True
    assert summary["live_order_allowed"] is False


def test_long_wave_stop_is_symmetric_and_never_loosened() -> None:
    tracker = PaperWaveStopComparisonTracker()
    started = datetime(2026, 8, 20, 1, tzinfo=UTC)
    tracker.start(
        trade_id="trade-2",
        side="BUY",
        entry_price=Decimal(100),
        fixed_stop_price=Decimal(80),
        observed_at=started,
    )
    tracker.observe(
        trade_id="trade-2", price=Decimal(110), observed_at=started + timedelta(seconds=3),
        wave_pivot_price=Decimal(90), buffer_points=Decimal(5),
    )
    tracker.observe(
        trade_id="trade-2", price=Decimal(112), observed_at=started + timedelta(seconds=6),
        wave_pivot_price=Decimal(95), buffer_points=Decimal(5),
    )
    assert tracker.active is not None
    assert tracker.active["wave_stop_price"] == "90"
    assert tracker.safe_payload()["live_order_allowed"] is False
