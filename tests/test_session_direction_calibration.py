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
    assert day["expectancy"] == "200.00"
    assert day["quality_gate_state"] == "normal"
    assert result["live_order_allowed"] is False


def test_two_losses_activate_only_matching_group_recovery() -> None:
    events = [
        event("entry", "one", "2026-08-21T01:00:00Z"),
        event("stop_loss_exit", "one", "2026-08-21T01:30:00Z", pnl=-100),
        event("entry", "two", "2026-08-21T02:00:00Z"),
        event("stop_loss_exit", "two", "2026-08-21T02:30:00Z", pnl=-200),
    ]
    result = build_session_direction_calibration(events, snapshot(), session="regular")
    day_long = result["groups"]["regular_LONG"]
    assert day_long["expectancy"] == "-150.00"
    assert day_long["consecutive_losses"] == 2
    assert day_long["quality_gate_state"] == "recovery"
    assert day_long["recommended_confirmation_candles"] == 3
    assert day_long["early_candidate_allowed"] is False
    assert result["groups"]["afterhours_LONG"]["quality_gate_state"] == "normal"


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


def test_inconsistent_pnl_is_excluded_from_calibration_statistics() -> None:
    entry = event("entry", "bad", "2026-08-21T01:00:00Z")
    entry.update({"quantity": 1, "point_value": 10, "entry_side": "buy"})
    exit_event = event(
        "stop_loss_exit", "bad", "2026-08-21T01:01:00Z", pnl=40
    )
    exit_event.update(
        {
            "quantity": 1,
            "point_value": 10,
            "entry_side": "sell",
            "current_price": 96,
            "stop_trigger_price": 90,
        }
    )

    result = build_session_direction_calibration(
        [entry, exit_event], snapshot(), session="regular"
    )

    group = result["groups"]["regular_LONG"]
    assert group["sample_size"] == 0
    assert group["excluded_anomalous_trades"] == 1
    assert group["statistics_integrity"] == "anomalies_excluded"
    assert result["excluded_anomalous_trades"] == 1
