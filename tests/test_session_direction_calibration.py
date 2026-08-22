from datetime import UTC, datetime

import pytest

from kam_market_ai.paper_trading.session_direction_calibration import (
    build_session_direction_calibration,
)


def event(
    event_type: str,
    trade_id: str,
    observed_at: str,
    *,
    entry: int = 100,
    stop: int = 90,
    pnl: int = 0,
) -> dict[str, object]:
    return {
        "event_type": event_type,
        "trade_id": trade_id,
        "observed_at": observed_at,
        "entry_price": entry,
        "stop_loss_price": stop,
        "realized_pnl": pnl,
    }


def snapshot() -> dict[str, object]:
    return {
        "market_data_only": True,
        "live_order_allowed": False,
        "analysis_preview": {
            "timeframes": {
                "1d": {"descending_trendline_state": "broken_above"},
                "60m": {"market_bias": "bullish"},
                "15m": {
                    "price_vs_ma20": "above",
                    "ma20_direction": "rising",
                    "volume_ratio_20": 1.3,
                },
            }
        },
    }


def test_calibrates_day_night_and_direction_without_double_counting() -> None:
    events = [
        event("entry", "day-long", "2026-08-21T01:00:00Z"),
        event("profit_lock_exit", "day-long", "2026-08-21T02:00:00Z", pnl=200),
        event("stop_loss_exit", "day-long", "2026-08-21T02:01:00Z", pnl=-999),
        event("entry", "night-short", "2026-08-21T12:00:00Z", stop=110),
        event("stop_loss_exit", "night-short", "2026-08-21T12:30:00Z", stop=110, pnl=-100),
    ]

    result = build_session_direction_calibration(
        events, snapshot(), session="afterhours"
    )

    day = result["groups"]["regular_LONG"]
    night = result["groups"]["afterhours_SHORT"]
    assert day["sample_size"] == 1
    assert day["calibrated_success_rate"] == 54.55
    assert night["sample_size"] == 1
    assert night["calibrated_success_rate"] == 45.45
    assert day["confidence"] == "insufficient"
    assert result["live_order_allowed"] is False


def test_line_and_volume_confirm_current_direction() -> None:
    result = build_session_direction_calibration([], snapshot(), session="regular")
    current = result["current_confirmation"]
    assert current["direction"] == "LONG"
    assert current["line_confirmation"] == "confirmed"
    assert current["volume_confirmation"] == "放量確認"
    assert current["bullish_ratio"] > current["bearish_ratio"]


def test_rejects_non_read_only_payload_and_invalid_session() -> None:
    unsafe = snapshot() | {"live_order_allowed": True}
    with pytest.raises(ValueError, match="read-only"):
        build_session_direction_calibration([], unsafe)
    with pytest.raises(ValueError, match="invalid calibration session"):
        build_session_direction_calibration([], snapshot(), session="unknown")


def test_timezone_aware_datetime_event_is_supported() -> None:
    entry = event("entry", "one", "2026-08-21T01:00:00Z")
    entry["observed_at"] = datetime(2026, 8, 21, 1, tzinfo=UTC)
    result = build_session_direction_calibration(
        [entry, event("take_profit_exit", "one", "2026-08-21T02:00:00Z", pnl=10)],
        snapshot(),
    )
    assert result["groups"]["regular_LONG"]["wins"] == 1
