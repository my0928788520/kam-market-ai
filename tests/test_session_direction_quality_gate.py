from datetime import UTC, datetime

from kam_market_ai.paper_trading.session_direction_quality_gate import (
    evaluate_session_direction_quality_gate,
)


def trade(trade_id: str, entry_at: str, pnl: int, *, short: bool = False) -> list[dict[str, object]]:
    entry = {
        "event_type": "entry",
        "trade_id": trade_id,
        "observed_at": entry_at,
        "entry_price": 100,
        "stop_loss_price": 110 if short else 90,
        "realized_pnl": 0,
    }
    exit_event = {
        **entry,
        "event_type": "stop_loss_exit" if pnl < 0 else "profit_lock_exit",
        "realized_pnl": pnl,
    }
    return [entry, exit_event]


def test_two_same_group_losses_shadow_only_early_candidate() -> None:
    events = [
        *trade("one", "2026-08-21T01:00:00Z", -200),
        *trade("two", "2026-08-21T02:00:00Z", -100),
    ]
    gate = evaluate_session_direction_quality_gate(
        events,
        observed_at=datetime(2026, 8, 21, 3, tzinfo=UTC),
        direction="LONG",
        opportunity_mode="PAPER_EARLY_CANDIDATE",
    )
    assert gate.group == "regular_LONG"
    assert gate.recovery_mode is True
    assert gate.action == "SHADOW_ONLY"
    assert gate.live_order_allowed is False


def test_recovery_keeps_full_signal_with_three_confirmations() -> None:
    events = [
        *trade("one", "2026-08-21T01:00:00Z", -200),
        *trade("two", "2026-08-21T02:00:00Z", -100),
    ]
    gate = evaluate_session_direction_quality_gate(
        events,
        observed_at=datetime(2026, 8, 21, 3, tzinfo=UTC),
        direction="LONG",
        opportunity_mode="PAPER_CANDIDATE",
    )
    assert gate.action == "REQUIRE_CONFIRMATION"
    assert gate.minimum_confirmation_candles == 3


def test_other_session_direction_is_not_penalized() -> None:
    events = [
        *trade("one", "2026-08-21T01:00:00Z", -200),
        *trade("two", "2026-08-21T02:00:00Z", -100),
    ]
    gate = evaluate_session_direction_quality_gate(
        events,
        observed_at=datetime(2026, 8, 21, 12, tzinfo=UTC),
        direction="SHORT",
        opportunity_mode="PAPER_EARLY_CANDIDATE",
    )
    assert gate.group == "afterhours_SHORT"
    assert gate.action == "ALLOW"
    assert gate.sample_size == 0


def test_profitable_recent_trade_clears_loss_streak() -> None:
    events = [
        *trade("one", "2026-08-21T01:00:00Z", -200),
        *trade("two", "2026-08-21T02:00:00Z", -100),
        *trade("three", "2026-08-21T03:00:00Z", 500),
    ]
    gate = evaluate_session_direction_quality_gate(
        events,
        observed_at=datetime(2026, 8, 21, 4, tzinfo=UTC),
        direction="LONG",
        opportunity_mode="PAPER_EARLY_CANDIDATE",
    )
    assert gate.recovery_mode is False
    assert gate.action == "ALLOW"
