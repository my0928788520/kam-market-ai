from datetime import UTC, datetime, timedelta
from decimal import Decimal
from hashlib import sha256
from json import dumps, loads
from types import MappingProxyType

import pytest

from kam_market_ai.live_read_only.five_timeframe_kam_rule_bridge import (
    MappedKamTimeframeState,
)
from kam_market_ai.market_data.fubon_five_timeframe_pipeline import (
    CompleteFiveTimeframeCandleResult,
    FiveTimeframe,
)
from kam_market_ai.models import Candle, Instrument
from kam_market_ai.paper_trading.five_timeframe_paper_direction import (
    decide_five_timeframe_paper_direction,
)
from kam_market_ai.paper_trading.live_tmf_simulation import (
    LEGACY_TMF_PAPER_JOURNAL_SCHEMA,
    LEGACY_TMF_PAPER_SIMULATION_VERSION,
    LIVE_TMF_PAPER_JOURNAL_SCHEMA,
    LIVE_TMF_PAPER_SIMULATION_VERSION,
    LiveTmfPaperSimulation,
    TmfPaperCycleAction,
    TmfPaperJournalStore,
    TmfPaperMarginStatus,
    TmfPaperPerformanceEventType,
    TmfPaperQuote,
    TmfPaperSimulationConfig,
    build_live_tmf_paper_quote,
)

NOW = datetime(2026, 8, 14, 5, 0, tzinfo=UTC)


def direction(code: str):
    states = tuple(
        MappedKamTimeframeState(timeframe, code, code[0], code[1], ())
        for timeframe in ("1w", "1d", "60m", "15m", "5m")
    )
    if code == "AU":
        return decide_five_timeframe_paper_direction(
            states,
            daily_ma60_position="above",
            m15_ma20_position="above",
            m15_ma20_direction="rising",
            m60_ma20_support="held",
            m60_market_bias="bullish",
        )
    if code == "BU":
        return decide_five_timeframe_paper_direction(
            states,
            daily_ma60_position="below",
            m15_ma20_position="below",
            m15_ma20_direction="falling",
            m60_ma20_support="broken",
            m60_market_bias="bearish",
        )
    return decide_five_timeframe_paper_direction(
        states,
        daily_ma60_position="insufficient",
        m15_ma20_position="insufficient",
        m15_ma20_direction="insufficient",
        m60_ma20_support="insufficient",
        m60_market_bias="insufficient",
    )


def quote(price: str, minute: int = 0) -> TmfPaperQuote:
    return TmfPaperQuote(
        "TMFH6",
        Decimal(price),
        NOW + timedelta(minutes=minute),
        f"{minute + int(Decimal(price)):064x}"[-64:],
    )


def config(
    *,
    enabled: bool = True,
    confirmed: bool = True,
    **overrides,
) -> TmfPaperSimulationConfig:
    return TmfPaperSimulationConfig(
        instrument="TMFH6",
        paper_trading_enabled=enabled,
        manual_approval_granted=confirmed,
        **overrides,
    )


def enter(session: LiveTmfPaperSimulation):
    return session.process_evaluation(direction("AU"), quote("22000"), evaluated_at=NOW)


def test_config_uses_current_taifex_tmf_margin_snapshot() -> None:
    value = config()

    assert value.initial_margin == Decimal(35050)
    assert value.maintenance_margin == Decimal(26900)
    assert value.margin_effective_at == datetime(2026, 8, 12, 5, 45, tzinfo=UTC)
    assert value.margin_source == "TAIFEX_INDEX_MARGIN_2026-08-12"


def test_live_risk_quote_is_auditable() -> None:
    value = build_live_tmf_paper_quote(
        instrument="TMFH6",
        price=Decimal(44779),
        observed_at=NOW,
    )

    assert value.price == Decimal(44779)
    assert value.price_policy == "FUBON_LATEST_VERIFIED_TRADE"
    assert len(value.quote_hash) == 64


def test_default_session_holds_without_kam_entry_condition() -> None:
    session = LiveTmfPaperSimulation(config())

    result = session.process_evaluation(direction("AF"), quote("22000"), evaluated_at=NOW)

    assert result.action is TmfPaperCycleAction.HOLD
    assert result.reason_codes == ("KAM_ENTRY_CONDITION_NOT_MET",)
    assert result.journal.events == ()


def test_entry_requires_distinct_confirming_candles_when_configured() -> None:
    session = LiveTmfPaperSimulation(config(entry_confirmation_candles=2))

    first = session.process_evaluation(direction("AU"), quote("22000"), evaluated_at=NOW)
    duplicate = session.process_evaluation(direction("AU"), quote("22000"), evaluated_at=NOW)
    confirmed = session.process_evaluation(
        direction("AU"),
        quote("22001", 5),
        evaluated_at=NOW + timedelta(minutes=5),
    )

    assert first.action is TmfPaperCycleAction.HOLD
    assert first.reason_codes == ("ENTRY_CONFIRMATION_PENDING",)
    assert duplicate.action is TmfPaperCycleAction.HOLD
    assert duplicate.reason_codes == ("ENTRY_CONFIRMATION_PENDING",)
    assert confirmed.action is TmfPaperCycleAction.ENTRY_FILLED


def test_same_forming_candle_price_change_does_not_confirm_entry() -> None:
    session = LiveTmfPaperSimulation(config(entry_confirmation_candles=2))
    first = TmfPaperQuote("TMFH6", Decimal("22000"), NOW, "a" * 64)
    changed_same_candle = TmfPaperQuote("TMFH6", Decimal("22005"), NOW, "b" * 64)

    session.process_evaluation(direction("AU"), first, evaluated_at=NOW)
    result = session.process_evaluation(
        direction("AU"), changed_same_candle, evaluated_at=NOW
    )

    assert result.action is TmfPaperCycleAction.HOLD
    assert result.reason_codes == ("ENTRY_CONFIRMATION_PENDING",)
    assert result.journal.events == ()


def test_out_of_order_older_candle_does_not_confirm_entry() -> None:
    session = LiveTmfPaperSimulation(config(entry_confirmation_candles=2))
    current = TmfPaperQuote("TMFH6", Decimal("22000"), NOW, "a" * 64)
    older = TmfPaperQuote(
        "TMFH6", Decimal("21999"), NOW - timedelta(minutes=5), "b" * 64
    )

    session.process_evaluation(direction("AU"), current, evaluated_at=NOW)
    result = session.process_evaluation(direction("AU"), older, evaluated_at=NOW)

    assert result.action is TmfPaperCycleAction.HOLD
    assert result.reason_codes == ("ENTRY_CONFIRMATION_PENDING",)
    assert result.journal.events == ()


@pytest.mark.parametrize(
    ("code", "first_price", "second_price", "third_price"),
    (
        ("AU", "22000", "21999", "22000"),
        ("BU", "22000", "22001", "22000"),
    ),
)
def test_second_candle_must_continue_in_trade_direction(
    code: str,
    first_price: str,
    second_price: str,
    third_price: str,
) -> None:
    session = LiveTmfPaperSimulation(config(entry_confirmation_candles=2))

    session.process_evaluation(direction(code), quote(first_price), evaluated_at=NOW)
    stalled = session.process_evaluation(
        direction(code),
        quote(second_price, 5),
        evaluated_at=NOW + timedelta(minutes=5),
    )
    confirmed = session.process_evaluation(
        direction(code),
        quote(third_price, 10),
        evaluated_at=NOW + timedelta(minutes=10),
    )

    assert stalled.action is TmfPaperCycleAction.HOLD
    assert stalled.reason_codes == ("ENTRY_PRICE_CONFIRMATION_PENDING",)
    assert confirmed.action is TmfPaperCycleAction.ENTRY_FILLED


@pytest.mark.parametrize(
    ("code", "first_price", "jump_price", "next_price"),
    (
        ("AU", "22000", "22021", "22022"),
        ("BU", "22000", "21979", "21978"),
    ),
)
def test_large_confirmation_move_resets_to_avoid_chasing(
    code: str,
    first_price: str,
    jump_price: str,
    next_price: str,
) -> None:
    session = LiveTmfPaperSimulation(config(entry_confirmation_candles=2))

    session.process_evaluation(direction(code), quote(first_price), evaluated_at=NOW)
    blocked = session.process_evaluation(
        direction(code),
        quote(jump_price, 5),
        evaluated_at=NOW + timedelta(minutes=5),
    )
    confirmed = session.process_evaluation(
        direction(code),
        quote(next_price, 10),
        evaluated_at=NOW + timedelta(minutes=10),
    )

    assert blocked.action is TmfPaperCycleAction.HOLD
    assert blocked.reason_codes == ("ENTRY_CONFIRMATION_MOVE_TOO_LARGE",)
    assert confirmed.action is TmfPaperCycleAction.ENTRY_FILLED


def test_entry_confirmation_resets_when_alignment_breaks_or_flips() -> None:
    session = LiveTmfPaperSimulation(config(entry_confirmation_candles=2))

    session.process_evaluation(direction("AU"), quote("22000"), evaluated_at=NOW)
    broken = session.process_evaluation(
        direction("AF"), quote("22001", 5), evaluated_at=NOW + timedelta(minutes=5)
    )
    restarted = session.process_evaluation(
        direction("AU"), quote("22002", 10), evaluated_at=NOW + timedelta(minutes=10)
    )
    flipped = session.process_evaluation(
        direction("BU"), quote("22001", 15), evaluated_at=NOW + timedelta(minutes=15)
    )

    assert broken.reason_codes == ("KAM_ENTRY_CONDITION_NOT_MET",)
    assert restarted.reason_codes == ("ENTRY_CONFIRMATION_PENDING",)
    assert flipped.reason_codes == ("ENTRY_CONFIRMATION_PENDING",)
    assert session.journal.events == ()


def test_entry_confirmation_config_rejects_invalid_values() -> None:
    with pytest.raises(ValueError, match="entry_confirmation_candles"):
        config(entry_confirmation_candles=0)
    with pytest.raises(ValueError, match="entry_confirmation_candles"):
        config(entry_confirmation_candles=True)
    with pytest.raises(ValueError, match="max_entry_confirmation_move_points"):
        config(max_entry_confirmation_move_points=Decimal(0))
    with pytest.raises(ValueError, match="Protection distances"):
        config(max_entry_confirmation_move_points=Decimal("20.5"))
    with pytest.raises(ValueError, match="volatile entry distance"):
        config(
            max_entry_confirmation_move_points=Decimal(20),
            volatile_entry_confirmation_move_points=Decimal(10),
        )


def test_dynamic_confirmation_enters_complete_signal_without_second_candle() -> None:
    session = LiveTmfPaperSimulation(
        config(
            entry_confirmation_candles=2,
            dynamic_entry_confirmation_enabled=True,
        )
    )

    result = session.process_evaluation(direction("AU"), quote("22000"), evaluated_at=NOW)

    assert result.action is TmfPaperCycleAction.ENTRY_FILLED
    assert result.live_order_allowed is False


def test_b_early_entry_requires_two_continuing_candles() -> None:
    early = decide_five_timeframe_paper_direction(
        tuple(
            MappedKamTimeframeState(timeframe, "ND", "N", "D", ())
            for timeframe in ("1w", "1d", "60m", "15m", "5m")
        ),
        m15_ma20_position="below",
        m15_ma20_direction="flat",
        m60_ma20_support="broken",
        m60_market_bias="bearish",
    )
    session = LiveTmfPaperSimulation(
        config(
            entry_confirmation_candles=2,
            dynamic_entry_confirmation_enabled=True,
        )
    )

    first = session.process_evaluation(early, quote("22000"), evaluated_at=NOW)
    confirmed = session.process_evaluation(
        early,
        quote("21999", 5),
        evaluated_at=NOW + timedelta(minutes=5),
    )

    assert first.action is TmfPaperCycleAction.HOLD
    assert confirmed.action is TmfPaperCycleAction.ENTRY_FILLED
    assert confirmed.live_order_allowed is False


def test_high_volatility_expands_confirmation_move_but_caps_at_40_points() -> None:
    early = decide_five_timeframe_paper_direction(
        tuple(
            MappedKamTimeframeState(timeframe, "ND", "N", "D", ())
            for timeframe in ("1w", "1d", "60m", "15m", "5m")
        ),
        m15_ma20_position="below",
        m15_ma20_direction="flat",
        m60_ma20_support="broken",
        m60_market_bias="bearish",
    )
    session = LiveTmfPaperSimulation(
        config(
            entry_confirmation_candles=2,
            dynamic_entry_confirmation_enabled=True,
        )
    )

    session.process_evaluation(
        early,
        quote("22000"),
        evaluated_at=NOW,
        entry_volatility_points=Decimal(18),
    )
    result = session.process_evaluation(
        early,
        quote("21965", 5),
        evaluated_at=NOW + timedelta(minutes=5),
        entry_volatility_points=Decimal(18),
    )

    assert result.action is TmfPaperCycleAction.ENTRY_FILLED
    assert result.live_order_allowed is False


def test_confirmed_short_direction_opens_a_paper_short() -> None:
    session = LiveTmfPaperSimulation(config())

    result = session.process_evaluation(direction("BU"), quote("22000"), evaluated_at=NOW)

    assert result.action is TmfPaperCycleAction.ENTRY_FILLED
    assert result.journal.ledger.positions[0].quantity == Decimal("-1")
    assert result.journal.ledger.cash_balance == Decimal("964950")
    assert result.performance_event is not None
    assert result.performance_event.stop_loss_price == Decimal("22020")
    assert result.performance_event.take_profit_price == Decimal("21960")


def test_short_stop_loss_and_take_profit_use_inverse_price_direction() -> None:
    stopped = LiveTmfPaperSimulation(config())
    stopped.process_evaluation(direction("BU"), quote("22000"), evaluated_at=NOW)
    stop_result = stopped.process_evaluation(
        direction("BF"),
        quote("22022", 1),
        evaluated_at=NOW + timedelta(minutes=1),
    )

    profitable = LiveTmfPaperSimulation(config())
    profitable.process_evaluation(direction("BU"), quote("22000"), evaluated_at=NOW)
    take_result = profitable.process_evaluation(
        direction("BF"),
        quote("21958", 1),
        evaluated_at=NOW + timedelta(minutes=1),
    )

    assert stop_result.action is TmfPaperCycleAction.EXIT_FILLED
    assert stop_result.performance_event is not None
    assert stop_result.performance_event.event_type is TmfPaperPerformanceEventType.STOP_LOSS_EXIT
    assert stop_result.performance_event.realized_pnl == Decimal("-220")
    assert stop_result.journal.ledger.cash_balance == Decimal("999780")
    assert take_result.action is TmfPaperCycleAction.EXIT_FILLED
    assert take_result.performance_event is not None
    assert take_result.performance_event.event_type is TmfPaperPerformanceEventType.TAKE_PROFIT_EXIT
    assert take_result.performance_event.realized_pnl == Decimal("420")
    assert take_result.journal.ledger.cash_balance == Decimal("1000420")


def test_buy_waits_when_paper_session_is_not_armed() -> None:
    session = LiveTmfPaperSimulation(config(enabled=False))

    result = enter(session)

    assert result.action is TmfPaperCycleAction.PENDING_MANUAL_CONFIRMATION
    assert result.reason_codes == ("PAPER_TRADING_NOT_ARMED",)
    assert result.proposal_hash is not None
    assert result.fill_hashes == ()


def test_buy_waits_for_manual_approval_even_when_paper_is_enabled() -> None:
    session = LiveTmfPaperSimulation(config(confirmed=False))

    result = enter(session)

    assert result.action is TmfPaperCycleAction.PENDING_MANUAL_CONFIRMATION
    assert result.reason_codes == ("MANUAL_CONFIRMATION_REQUIRED",)
    assert result.journal.events == ()


def test_confirmed_natural_buy_reserves_margin_and_keeps_fill_price() -> None:
    session = LiveTmfPaperSimulation(config())

    result = enter(session)

    assert result.action is TmfPaperCycleAction.ENTRY_FILLED
    assert result.fill_hashes
    assert len(result.journal.ledger.positions) == 1
    assert result.journal.ledger.positions[0].average_price == Decimal(22000)
    assert result.journal.ledger.cash_balance == Decimal(964950)
    assert result.journal.ledger.cash_entries[-1].cash_delta == Decimal(-35050)
    assert result.journal.reserved_margin == Decimal(35050)
    assert result.journal.required_maintenance_margin == Decimal(26900)
    assert result.journal.account_equity == Decimal(1000000)
    assert result.journal.margin_status is TmfPaperMarginStatus.SAFE
    event = result.performance_event
    assert event is not None
    assert event.event_type is TmfPaperPerformanceEventType.ENTRY
    assert event.stop_loss_price == Decimal(21980)
    assert event.take_profit_price == Decimal(22040)
    assert event.point_value == Decimal(10)
    boundary = result.safe_payload()["execution_boundary"]
    assert boundary == {
        "mode": "paper_only",
        "automatic_paper_execution": True,
        "real_order_requires_human_action": True,
        "broker_submission_available": False,
        "live_order_allowed": False,
    }


def test_entry_fails_closed_when_initial_margin_is_not_available() -> None:
    session = LiveTmfPaperSimulation(config(initial_cash=Decimal(35049)))

    result = enter(session)

    assert result.action is TmfPaperCycleAction.REJECTED
    assert result.reason_codes == ("INSUFFICIENT_INITIAL_MARGIN",)
    assert result.journal.ledger.cash_balance == Decimal(35049)
    assert not result.journal.ledger.positions
    assert result.journal.events == ()


def test_repeated_three_second_refresh_does_not_duplicate_the_entry() -> None:
    session = LiveTmfPaperSimulation(config())
    first = enter(session)

    repeated = session.process_evaluation(direction("AU"), quote("22000"), evaluated_at=NOW)

    assert first.action is TmfPaperCycleAction.ENTRY_FILLED
    assert repeated.action is TmfPaperCycleAction.DUPLICATE_IGNORED
    assert len(repeated.journal.events) == 1
    assert len(repeated.journal.ledger.cash_entries) == 1


def test_new_quote_marks_unrealized_pnl_mfe_and_hash_chain() -> None:
    session = LiveTmfPaperSimulation(config())
    enter(session)

    result = session.process_evaluation(
        direction("AF"),
        quote("22010", 1),
        evaluated_at=NOW + timedelta(minutes=1),
    )

    assert result.action is TmfPaperCycleAction.POSITION_MARKED
    event = result.performance_event
    assert event is not None
    assert event.unrealized_pnl == Decimal(100)
    assert event.max_favorable_excursion == Decimal(100)
    assert event.max_adverse_excursion == Decimal(0)
    assert event.previous_event_hash == result.journal.events[0].event_hash
    assert len(result.journal.ledger.cash_entries) == 1


def test_stop_loss_quote_closes_position_and_records_realized_loss() -> None:
    session = LiveTmfPaperSimulation(config())
    enter(session)

    result = session.process_evaluation(
        direction("AF"),
        quote("21978", 1),
        evaluated_at=NOW + timedelta(minutes=1),
    )

    assert result.action is TmfPaperCycleAction.EXIT_FILLED
    assert not result.journal.ledger.positions
    event = result.performance_event
    assert event is not None
    assert event.event_type is TmfPaperPerformanceEventType.STOP_LOSS_EXIT
    assert event.realized_pnl == Decimal(-220)
    assert event.max_adverse_excursion == Decimal(-220)
    assert result.journal.ledger.cash_balance == Decimal(999780)
    assert result.journal.ledger.cash_entries[-1].cash_delta == Decimal(34830)
    assert result.journal.reserved_margin == Decimal(0)
    assert result.journal.margin_status is TmfPaperMarginStatus.NO_POSITION


def test_take_profit_quote_closes_position_and_records_realized_gain() -> None:
    session = LiveTmfPaperSimulation(config(trend_hold_enabled=False))
    enter(session)

    result = session.process_evaluation(
        direction("AU"),
        quote("22042", 1),
        evaluated_at=NOW + timedelta(minutes=1),
    )

    assert result.action is TmfPaperCycleAction.EXIT_FILLED
    event = result.performance_event
    assert event is not None
    assert event.event_type is TmfPaperPerformanceEventType.TAKE_PROFIT_EXIT
    assert event.realized_pnl == Decimal(420)
    assert event.max_favorable_excursion == Decimal(420)
    assert result.journal.ledger.cash_balance == Decimal(1000420)
    assert result.journal.ledger.cash_entries[-1].cash_delta == Decimal(35470)


def test_aligned_long_extends_take_profit_and_locks_twenty_points() -> None:
    session = LiveTmfPaperSimulation(config())
    enter(session)

    extended = session.process_evaluation(
        direction("AU"), quote("22040", 1), evaluated_at=NOW + timedelta(minutes=1)
    )

    assert extended.action is TmfPaperCycleAction.POSITION_MARKED
    assert extended.reason_codes == ("TREND_HOLD_TAKE_PROFIT_EXTENDED",)
    assert extended.performance_event is not None
    assert extended.performance_event.stop_loss_price == Decimal("22020")
    assert extended.performance_event.take_profit_price == Decimal("22060")


def test_profitable_trailing_stop_is_named_profit_lock_and_not_counted_as_loss() -> None:
    session = LiveTmfPaperSimulation(
        config(
            reentry_cooldown_minutes=0,
            max_consecutive_stop_losses_per_risk_day=1,
        )
    )
    enter(session)
    session.process_evaluation(
        direction("AU"), quote("22040", 1), evaluated_at=NOW + timedelta(minutes=1)
    )

    exited = session.process_evaluation(
        direction("AU"), quote("22018", 2), evaluated_at=NOW + timedelta(minutes=2)
    )
    reopened = session.process_evaluation(
        direction("AU"), quote("22019", 3), evaluated_at=NOW + timedelta(minutes=3)
    )

    assert exited.action is TmfPaperCycleAction.EXIT_FILLED
    assert exited.performance_event is not None
    assert (
        exited.performance_event.event_type
        is TmfPaperPerformanceEventType.PROFIT_LOCK_EXIT
    )
    assert exited.performance_event.realized_pnl == Decimal("180")
    assert exited.reason_codes == ("PROFIT_LOCK_EXIT",)
    assert reopened.action is TmfPaperCycleAction.ENTRY_FILLED
    assert reopened.safe_payload()["performance_summary"]["exit_breakdown"] == {
        "profit_lock": 1,
        "loss_stop": 0,
        "take_profit": 0,
        "rule_exit": 0,
    }


def test_profit_reentry_requires_pullback_then_reclaim_in_same_direction() -> None:
    session = LiveTmfPaperSimulation(
        config(
            reentry_cooldown_minutes=0,
            same_direction_profit_reentry_enabled=True,
            profit_reentry_pullback_points=Decimal(10),
        )
    )
    enter(session)
    session.process_evaluation(
        direction("AU"), quote("22040", 1), evaluated_at=NOW + timedelta(minutes=1)
    )
    session.process_evaluation(
        direction("AU"), quote("22018", 2), evaluated_at=NOW + timedelta(minutes=2)
    )

    waiting_pullback = session.process_evaluation(
        direction("AU"), quote("22017", 3), evaluated_at=NOW + timedelta(minutes=3)
    )
    waiting_reclaim = session.process_evaluation(
        direction("AU"), quote("22008", 4), evaluated_at=NOW + timedelta(minutes=4)
    )
    reopened = session.process_evaluation(
        direction("AU"), quote("22018", 5), evaluated_at=NOW + timedelta(minutes=5)
    )

    assert waiting_pullback.action is TmfPaperCycleAction.HOLD
    assert waiting_pullback.reason_codes == ("PROFIT_REENTRY_WAITING_FOR_PULLBACK",)
    assert waiting_reclaim.action is TmfPaperCycleAction.HOLD
    assert waiting_reclaim.reason_codes == ("PROFIT_REENTRY_WAITING_FOR_RECLAIM",)
    assert reopened.action is TmfPaperCycleAction.ENTRY_FILLED
    assert reopened.journal.open_entry is not None
    assert reopened.journal.open_entry.entry_price == Decimal("22018")
    assert reopened.journal.ledger.live_order_allowed is False


def test_aligned_short_extends_take_profit_downward_symmetrically() -> None:
    session = LiveTmfPaperSimulation(config())
    session.process_evaluation(direction("BU"), quote("22000"), evaluated_at=NOW)

    extended = session.process_evaluation(
        direction("BU"), quote("21960", 1), evaluated_at=NOW + timedelta(minutes=1)
    )

    assert extended.action is TmfPaperCycleAction.POSITION_MARKED
    assert extended.performance_event is not None
    assert extended.performance_event.stop_loss_price == Decimal("21980")
    assert extended.performance_event.take_profit_price == Decimal("21940")


def test_trend_hold_moves_target_beyond_a_gap_quote() -> None:
    session = LiveTmfPaperSimulation(config())
    enter(session)

    extended = session.process_evaluation(
        direction("AU"), quote("22080", 1), evaluated_at=NOW + timedelta(minutes=1)
    )

    assert extended.performance_event is not None
    assert extended.performance_event.stop_loss_price == Decimal("22060")
    assert extended.performance_event.take_profit_price == Decimal("22100")


def test_take_profit_exits_when_five_timeframes_are_no_longer_aligned() -> None:
    session = LiveTmfPaperSimulation(config())
    enter(session)

    result = session.process_evaluation(
        direction("AF"), quote("22040", 1), evaluated_at=NOW + timedelta(minutes=1)
    )

    assert result.action is TmfPaperCycleAction.EXIT_FILLED
    assert result.performance_event is not None
    assert result.performance_event.event_type is TmfPaperPerformanceEventType.TAKE_PROFIT_EXIT
    assert result.performance_event.realized_pnl == Decimal("400")


def test_performance_summary_separates_long_short_and_requires_evidence() -> None:
    session = LiveTmfPaperSimulation(config(reentry_cooldown_minutes=0))
    enter(session)
    session.process_evaluation(
        direction("AF"),
        quote("22042", 1),
        evaluated_at=NOW + timedelta(minutes=1),
    )
    session.process_evaluation(
        direction("BU"),
        quote("22041", 2),
        evaluated_at=NOW + timedelta(minutes=2),
    )
    result = session.process_evaluation(
        direction("BF"),
        quote("22063", 3),
        evaluated_at=NOW + timedelta(minutes=3),
    )

    summary = result.safe_payload()["performance_summary"]

    assert summary["sample_size"] == 2
    assert summary["minimum_sample_size"] == 30
    assert summary["win_rate"] == "50.00"
    assert summary["net_pnl"] == "200"
    assert summary["expectancy"] == "100.00"
    assert summary["profit_factor"] == "1.91"
    assert summary["maximum_drawdown"] == "220"
    assert summary["average_win"] == "420.00"
    assert summary["average_loss"] == "220.00"
    assert summary["profit_retention_rate"] == "100.00"
    assert summary["stop_quality"] == "持續累積比較樣本"
    assert summary["shadow_fixed_stop_touches"] == 1
    assert summary["shadow_avoided_premature_exits"] == 0
    assert summary["shadow_incremental_pnl"] == "0"
    assert summary["exit_breakdown"] == {
        "profit_lock": 0,
        "loss_stop": 1,
        "take_profit": 1,
        "rule_exit": 0,
    }
    assert summary["long"]["net_pnl"] == "420"
    assert summary["short"]["net_pnl"] == "-220"
    assert summary["adjustment_allowed"] is False
    assert summary["live_order_allowed"] is False


def test_exit_cooldown_prevents_immediate_reentry_and_allows_later_entry() -> None:
    session = LiveTmfPaperSimulation(config(reentry_cooldown_minutes=15))
    enter(session)
    exited = session.process_evaluation(
        direction("AF"),
        quote("21978", 1),
        evaluated_at=NOW + timedelta(minutes=1),
    )

    blocked = session.process_evaluation(
        direction("AU"),
        quote("21979", 2),
        evaluated_at=NOW + timedelta(minutes=2),
    )
    reopened = session.process_evaluation(
        direction("AU"),
        quote("21980", 16),
        evaluated_at=NOW + timedelta(minutes=16),
    )

    assert exited.action is TmfPaperCycleAction.EXIT_FILLED
    assert blocked.action is TmfPaperCycleAction.HOLD
    assert blocked.reason_codes == ("REENTRY_COOLDOWN_ACTIVE",)
    assert len(blocked.journal.events) == 2
    assert reopened.action is TmfPaperCycleAction.ENTRY_FILLED
    assert len(reopened.journal.ledger.positions) == 1


def test_reentry_cooldown_config_rejects_invalid_values() -> None:
    with pytest.raises(ValueError, match="reentry_cooldown_minutes"):
        config(reentry_cooldown_minutes=-1)
    with pytest.raises(ValueError, match="reentry_cooldown_minutes"):
        config(reentry_cooldown_minutes=True)


def test_daily_loss_limit_blocks_same_risk_day_and_resets_next_risk_day() -> None:
    session = LiveTmfPaperSimulation(
        config(max_daily_loss=Decimal("200"), reentry_cooldown_minutes=15)
    )
    enter(session)
    stopped = session.process_evaluation(
        direction("AF"),
        quote("21978", 1),
        evaluated_at=NOW + timedelta(minutes=1),
    )

    blocked = session.process_evaluation(
        direction("AU"),
        quote("21980", 16),
        evaluated_at=NOW + timedelta(minutes=16),
    )
    next_day = session.process_evaluation(
        direction("AU"),
        quote("21981", 24 * 60 + 16),
        evaluated_at=NOW + timedelta(days=1, minutes=16),
    )

    assert stopped.performance_event is not None
    assert stopped.performance_event.realized_pnl == Decimal("-220")
    assert blocked.action is TmfPaperCycleAction.REJECTED
    assert blocked.reason_codes == ("MAX_DAILY_LOSS_EXCEEDED",)
    assert next_day.action is TmfPaperCycleAction.ENTRY_FILLED


def test_taiwan_risk_day_keeps_overnight_session_losses_together() -> None:
    session = LiveTmfPaperSimulation(
        config(max_daily_loss=Decimal("200"), reentry_cooldown_minutes=0)
    )
    night_start = datetime(2026, 8, 14, 19, 0, tzinfo=UTC)
    night_quote = TmfPaperQuote("TMFH6", Decimal("22000"), night_start, "a" * 64)
    session.process_evaluation(direction("AU"), night_quote, evaluated_at=night_start)
    exit_time = night_start + timedelta(minutes=1)
    session.process_evaluation(
        direction("AF"),
        TmfPaperQuote("TMFH6", Decimal("21978"), exit_time, "b" * 64),
        evaluated_at=exit_time,
    )

    before_boundary = night_start + timedelta(hours=2)
    blocked = session.process_evaluation(
        direction("AU"),
        TmfPaperQuote("TMFH6", Decimal("21980"), before_boundary, "c" * 64),
        evaluated_at=before_boundary,
    )

    assert blocked.action is TmfPaperCycleAction.REJECTED
    assert blocked.reason_codes == ("MAX_DAILY_LOSS_EXCEEDED",)


def test_daily_entry_limit_blocks_overtrading_and_resets_next_risk_day() -> None:
    session = LiveTmfPaperSimulation(
        config(max_entries_per_risk_day=3, reentry_cooldown_minutes=0)
    )
    for entry_minute in (0, 2, 4):
        entered = session.process_evaluation(
            direction("AU"),
            quote("22000", entry_minute),
            evaluated_at=NOW + timedelta(minutes=entry_minute),
        )
        exited = session.process_evaluation(
            direction("AF"),
            quote("22042", entry_minute + 1),
            evaluated_at=NOW + timedelta(minutes=entry_minute + 1),
        )
        assert entered.action is TmfPaperCycleAction.ENTRY_FILLED
        assert exited.action is TmfPaperCycleAction.EXIT_FILLED

    blocked = session.process_evaluation(
        direction("BU"),
        quote("22000", 6),
        evaluated_at=NOW + timedelta(minutes=6),
    )
    next_day = session.process_evaluation(
        direction("BU"),
        quote("22000", 24 * 60 + 6),
        evaluated_at=NOW + timedelta(days=1, minutes=6),
    )

    assert blocked.action is TmfPaperCycleAction.REJECTED
    assert blocked.reason_codes == ("MAX_DAILY_ENTRIES_EXCEEDED",)
    assert next_day.action is TmfPaperCycleAction.ENTRY_FILLED
    assert next_day.journal.ledger.positions[0].quantity == Decimal("-1")


def test_daily_entry_limit_rejects_invalid_configuration() -> None:
    with pytest.raises(ValueError, match="max_entries_per_risk_day"):
        config(max_entries_per_risk_day=0)
    with pytest.raises(ValueError, match="max_entries_per_risk_day"):
        config(max_entries_per_risk_day=True)


def test_two_consecutive_stop_losses_block_same_risk_day() -> None:
    session = LiveTmfPaperSimulation(
        config(
            max_consecutive_stop_losses_per_risk_day=2,
            max_entries_per_risk_day=3,
            reentry_cooldown_minutes=0,
        )
    )
    for entry_minute in (0, 2):
        entered = session.process_evaluation(
            direction("AU"),
            quote("22000", entry_minute),
            evaluated_at=NOW + timedelta(minutes=entry_minute),
        )
        stopped = session.process_evaluation(
            direction("AF"),
            quote("21978", entry_minute + 1),
            evaluated_at=NOW + timedelta(minutes=entry_minute + 1),
        )
        assert entered.action is TmfPaperCycleAction.ENTRY_FILLED
        assert stopped.performance_event is not None
        assert (
            stopped.performance_event.event_type
            is TmfPaperPerformanceEventType.STOP_LOSS_EXIT
        )

    blocked = session.process_evaluation(
        direction("AU"),
        quote("22000", 4),
        evaluated_at=NOW + timedelta(minutes=4),
    )

    assert blocked.action is TmfPaperCycleAction.REJECTED
    assert blocked.reason_codes == ("CONSECUTIVE_STOP_LOSS_LIMIT_REACHED",)
    assert len(blocked.journal.events) == 4


def test_take_profit_breaks_stop_loss_streak_and_next_risk_day_resets() -> None:
    session = LiveTmfPaperSimulation(
        config(
            max_consecutive_stop_losses_per_risk_day=2,
            max_entries_per_risk_day=5,
            reentry_cooldown_minutes=0,
        )
    )
    for entry_minute, exit_price in ((0, "21978"), (2, "22042"), (4, "21978")):
        session.process_evaluation(
            direction("AU"),
            quote("22000", entry_minute),
            evaluated_at=NOW + timedelta(minutes=entry_minute),
        )
        session.process_evaluation(
            direction("AF"),
            quote(exit_price, entry_minute + 1),
            evaluated_at=NOW + timedelta(minutes=entry_minute + 1),
        )

    same_day = session.process_evaluation(
        direction("AU"),
        quote("22000", 6),
        evaluated_at=NOW + timedelta(minutes=6),
    )
    assert same_day.action is TmfPaperCycleAction.ENTRY_FILLED

    session.process_evaluation(
        direction("AF"),
        quote("21978", 7),
        evaluated_at=NOW + timedelta(minutes=7),
    )
    blocked = session.process_evaluation(
        direction("AU"),
        quote("22000", 8),
        evaluated_at=NOW + timedelta(minutes=8),
    )
    next_day = session.process_evaluation(
        direction("AU"),
        quote("22000", 24 * 60 + 8),
        evaluated_at=NOW + timedelta(days=1, minutes=8),
    )

    assert blocked.reason_codes == ("CONSECUTIVE_STOP_LOSS_LIMIT_REACHED",)
    assert next_day.action is TmfPaperCycleAction.ENTRY_FILLED


def test_consecutive_stop_loss_limit_rejects_invalid_configuration() -> None:
    with pytest.raises(ValueError, match="max_consecutive_stop_losses_per_risk_day"):
        config(max_consecutive_stop_losses_per_risk_day=0)
    with pytest.raises(ValueError, match="max_consecutive_stop_losses_per_risk_day"):
        config(max_consecutive_stop_losses_per_risk_day=True)


def test_margin_warning_is_recorded_before_stop_when_margin_equity_is_too_low() -> None:
    session = LiveTmfPaperSimulation(config(stop_loss_points=Decimal(1000)))
    enter(session)

    result = session.process_evaluation(
        direction("AF"),
        quote("21184", 1),
        evaluated_at=NOW + timedelta(minutes=1),
    )

    assert result.action is TmfPaperCycleAction.POSITION_MARKED
    assert result.reason_codes == ("MARGIN_MAINTENANCE_WARNING",)
    assert result.journal.margin_status is TmfPaperMarginStatus.MAINTENANCE_WARNING
    assert result.journal.account_equity == Decimal(991840)


def test_stale_future_and_off_tick_quotes_fail_closed() -> None:
    session = LiveTmfPaperSimulation(config())

    stale = session.process_evaluation(
        direction("AU"),
        quote("22000"),
        evaluated_at=NOW + timedelta(minutes=7),
    )
    future = session.process_evaluation(
        direction("AU"),
        quote("22000", 1),
        evaluated_at=NOW,
    )
    off_tick = session.process_evaluation(
        direction("AU"),
        quote("22000.5"),
        evaluated_at=NOW,
    )

    assert stale.reason_codes == ("QUOTE_STALE",)
    assert future.reason_codes == ("QUOTE_FROM_FUTURE",)
    assert off_tick.reason_codes == ("QUOTE_NOT_ON_TICK",)
    assert session.journal.events == ()


def test_journal_round_trip_preserves_ledger_events_and_hash(tmp_path) -> None:
    store = TmfPaperJournalStore(tmp_path / "tmf.json")
    session = LiveTmfPaperSimulation(config(), store=store)
    enter(session)
    session.process_evaluation(
        direction("AF"),
        quote("22010", 1),
        evaluated_at=NOW + timedelta(minutes=1),
    )

    restored = store.load(config())
    payload = loads(store.path.read_text(encoding="utf-8"))

    assert payload["schema"] == LIVE_TMF_PAPER_JOURNAL_SCHEMA
    assert payload["version"] == LIVE_TMF_PAPER_SIMULATION_VERSION
    assert payload["margin_requirement"]["initial_margin"] == "35050"
    assert payload["margin_state"]["reserved_margin"] == "35050"
    assert restored.journal_hash == session.journal.journal_hash
    assert restored.ledger.ledger_hash == session.journal.ledger.ledger_hash
    assert len(restored.events) == 2


def test_existing_empty_v1_journal_is_verified_and_migrated(tmp_path) -> None:
    store = TmfPaperJournalStore(tmp_path / "tmf.json")
    legacy_ledger = {
        "cash_balance": "1000000",
        "positions": [],
        "cash_entries": [],
        "used_idempotency_keys": [],
        "allow_negative_cash": False,
        "allow_short": False,
        "dry_run": True,
        "live_order_allowed": False,
        "broker_connected": False,
        "account_credentials_allowed": False,
    }
    ledger_hash = sha256(
        dumps(
            legacy_ledger,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        ).encode("utf-8")
    ).hexdigest()
    legacy_canonical = {
        "version": LEGACY_TMF_PAPER_SIMULATION_VERSION,
        "instrument": "TMFH6",
        "point_value": "10",
        "ledger": legacy_ledger,
        "ledger_hash": ledger_hash,
        "events": [],
    }
    legacy_payload = {
        "schema": LEGACY_TMF_PAPER_JOURNAL_SCHEMA,
        **legacy_canonical,
        "journal_hash": sha256(
            dumps(
                legacy_canonical,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=True,
            ).encode("utf-8")
        ).hexdigest(),
    }
    store.path.write_text(dumps(legacy_payload), encoding="utf-8")

    restored = store.load(config())
    store.save(restored)
    migrated = loads(store.path.read_text(encoding="utf-8"))

    assert restored.ledger.cash_balance == Decimal(1000000)
    assert restored.margin_requirement.initial_margin == Decimal(35050)
    assert restored.events == ()
    assert migrated["schema"] == LIVE_TMF_PAPER_JOURNAL_SCHEMA
    assert migrated["version"] == LIVE_TMF_PAPER_SIMULATION_VERSION


def test_tampered_journal_is_rejected_instead_of_silently_loaded(tmp_path) -> None:
    store = TmfPaperJournalStore(tmp_path / "tmf.json")
    session = LiveTmfPaperSimulation(config(), store=store)
    enter(session)
    payload = loads(store.path.read_text(encoding="utf-8"))
    payload["ledger"]["cash_balance"] = "999999"
    store.path.write_text(dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="PAPER_JOURNAL_INVALID"):
        store.load(config())


def test_cycle_payload_keeps_all_live_execution_flags_false() -> None:
    payload = enter(LiveTmfPaperSimulation(config())).safe_payload()

    assert payload["dry_run"] is True
    assert payload["live_order_allowed"] is False
    assert payload["broker_connected"] is False
    assert payload["account_credentials_allowed"] is False
    assert payload["margin_requirement"]["initial_margin"] == "35050"
    assert payload["margin_state"]["reserved_margin"] == "35050"
    assert payload["margin_state"]["status"] == "safe"
    assert len(payload["audit_hash"]) == 64


def test_candle_entrypoint_uses_natural_kam_result_without_forcing_buy() -> None:
    durations = {
        FiveTimeframe.M5: timedelta(minutes=5),
        FiveTimeframe.M15: timedelta(minutes=15),
        FiveTimeframe.M60: timedelta(hours=1),
        FiveTimeframe.DAY: timedelta(days=1),
        FiveTimeframe.WEEK: timedelta(days=7),
    }
    series = {
        timeframe: (
            Candle(
                Instrument.TMF,
                NOW - duration,
                NOW,
                22000,
                22010,
                21990,
                22000,
                10,
            ),
        )
        for timeframe, duration in durations.items()
    }
    candles = CompleteFiveTimeframeCandleResult(
        Instrument.TMF,
        None,
        MappingProxyType(series),
        3,
    )
    session = LiveTmfPaperSimulation(config())

    result = session.process_candles(candles, evaluated_at=NOW)

    assert result.action is TmfPaperCycleAction.HOLD
    assert result.direction == "HOLD"
    assert result.journal.events == ()


def test_open_position_waits_for_five_minute_structure_or_emergency_stop() -> None:
    durations = {
        FiveTimeframe.M5: timedelta(minutes=5),
        FiveTimeframe.M15: timedelta(minutes=15),
        FiveTimeframe.M60: timedelta(hours=1),
        FiveTimeframe.DAY: timedelta(days=1),
        FiveTimeframe.WEEK: timedelta(days=7),
    }
    candles = CompleteFiveTimeframeCandleResult(
        Instrument.TMF,
        None,
        MappingProxyType(
            {
                timeframe: (
                    Candle(
                        Instrument.TMF,
                        NOW - duration,
                        NOW,
                        22000,
                        22010,
                        21990,
                        22000,
                        10,
                    ),
                )
                for timeframe, duration in durations.items()
            }
        ),
        3,
    )
    session = LiveTmfPaperSimulation(config())
    assert (
        session.process_open_position_quote(
            candles,
            build_live_tmf_paper_quote(
                instrument="TMFH6",
                price=Decimal(21980),
                observed_at=NOW + timedelta(seconds=3),
            ),
            evaluated_at=NOW + timedelta(seconds=3),
        )
        is None
    )

    enter(session)
    tested = session.process_open_position_quote(
        candles,
        build_live_tmf_paper_quote(
            instrument="TMFH6",
            price=Decimal(21980),
            observed_at=NOW + timedelta(seconds=3),
        ),
        evaluated_at=NOW + timedelta(seconds=3),
    )

    assert tested is not None
    assert tested.action is TmfPaperCycleAction.POSITION_MARKED
    assert tested.reason_codes == ("STRUCTURAL_STOP_TESTED_WAITING_FOR_5M_CLOSE",)
    assert tested.journal.ledger.positions

    stopped = session.process_open_position_quote(
        candles,
        build_live_tmf_paper_quote(
            instrument="TMFH6",
            price=Decimal(21959),
            observed_at=NOW + timedelta(seconds=6),
        ),
        evaluated_at=NOW + timedelta(seconds=6),
    )

    assert stopped is not None
    assert stopped.action is TmfPaperCycleAction.EXIT_FILLED
    assert stopped.performance_event is not None
    assert (
        stopped.performance_event.event_type
        is TmfPaperPerformanceEventType.STOP_LOSS_EXIT
    )
    assert stopped.journal.ledger.positions == ()

    close_confirmed_session = LiveTmfPaperSimulation(config())
    enter(close_confirmed_session)
    confirmed_series = dict(candles.series)
    confirmed_series[FiveTimeframe.M5] = (
        Candle(
            Instrument.TMF,
            NOW,
            NOW + timedelta(minutes=5),
            22000,
            22005,
            21975,
            21979,
            10,
        ),
    )
    confirmed_candles = CompleteFiveTimeframeCandleResult(
        Instrument.TMF,
        None,
        MappingProxyType(confirmed_series),
        3,
    )
    confirmed = close_confirmed_session.process_open_position_quote(
        confirmed_candles,
        build_live_tmf_paper_quote(
            instrument="TMFH6",
            price=Decimal(21979),
            observed_at=NOW + timedelta(minutes=5, seconds=3),
        ),
        evaluated_at=NOW + timedelta(minutes=5, seconds=3),
    )

    assert confirmed is not None
    assert confirmed.action is TmfPaperCycleAction.EXIT_FILLED
    assert confirmed.performance_event is not None
    assert confirmed.performance_event.event_type is TmfPaperPerformanceEventType.STOP_LOSS_EXIT


def test_open_position_uses_latest_confirmed_equal_wave_pivot_before_exit() -> None:
    session = LiveTmfPaperSimulation(config())
    enter(session)
    five_minute = tuple(
        Candle(
            Instrument.TMF,
            NOW + timedelta(minutes=index * 5),
            NOW + timedelta(minutes=(index + 1) * 5),
            21980,
            high,
            low,
            21975,
            10,
        )
        for index, (high, low) in enumerate(
            ((22000, 21980), (21990, 21960), (21985, 21940), (21988, 21955), (21992, 21970))
        )
    )
    durations = {
        FiveTimeframe.M15: timedelta(minutes=15),
        FiveTimeframe.M60: timedelta(hours=1),
        FiveTimeframe.DAY: timedelta(days=1),
        FiveTimeframe.WEEK: timedelta(days=7),
    }
    series = {FiveTimeframe.M5: five_minute}
    series.update({
        timeframe: (
            Candle(Instrument.TMF, NOW - duration, NOW, 22000, 22010, 21990, 22000, 10),
        )
        for timeframe, duration in durations.items()
    })
    candles = CompleteFiveTimeframeCandleResult(
        Instrument.TMF,
        None,
        MappingProxyType(series),
        3,
    )
    evaluated_at = NOW + timedelta(minutes=25, seconds=3)

    held = session.process_open_position_quote(
        candles,
        build_live_tmf_paper_quote(
            instrument="TMFH6",
            price=Decimal(21955),
            observed_at=evaluated_at,
        ),
        evaluated_at=evaluated_at,
    )

    assert held is not None
    assert held.action is TmfPaperCycleAction.POSITION_MARKED
    assert held.performance_event is not None
    assert held.performance_event.stop_loss_price == Decimal(21940)
    assert held.journal.ledger.positions

    recovered = session.process_evaluation(
        direction("AF"),
        quote("22040", 26),
        evaluated_at=NOW + timedelta(minutes=26),
    )
    shadow = recovered.safe_payload()["performance_summary"]
    assert recovered.action is TmfPaperCycleAction.EXIT_FILLED
    assert shadow["stop_quality"] == "波浪保護有效"
    assert shadow["shadow_fixed_stop_touches"] == 1
    assert shadow["shadow_avoided_premature_exits"] == 1
    assert shadow["shadow_incremental_pnl"] == "600"


def test_short_position_uses_confirmed_equal_wave_high_symmetrically() -> None:
    session = LiveTmfPaperSimulation(config())
    entered = session.process_evaluation(direction("BU"), quote("22000"), evaluated_at=NOW)
    assert entered.action is TmfPaperCycleAction.ENTRY_FILLED
    five_minute = tuple(
        Candle(
            Instrument.TMF,
            NOW + timedelta(minutes=index * 5),
            NOW + timedelta(minutes=(index + 1) * 5),
            22020,
            high,
            low,
            22025,
            10,
        )
        for index, (high, low) in enumerate(
            ((22020, 22000), (22040, 22005), (22060, 22010), (22045, 22008), (22035, 22000))
        )
    )
    series = {FiveTimeframe.M5: five_minute}
    for timeframe, duration in (
        (FiveTimeframe.M15, timedelta(minutes=15)),
        (FiveTimeframe.M60, timedelta(hours=1)),
        (FiveTimeframe.DAY, timedelta(days=1)),
        (FiveTimeframe.WEEK, timedelta(days=7)),
    ):
        series[timeframe] = (
            Candle(Instrument.TMF, NOW - duration, NOW, 22000, 22010, 21990, 22000, 10),
        )
    candles = CompleteFiveTimeframeCandleResult(
        Instrument.TMF, None, MappingProxyType(series), 3
    )
    evaluated_at = NOW + timedelta(minutes=25, seconds=3)

    held = session.process_open_position_quote(
        candles,
        build_live_tmf_paper_quote(
            instrument="TMFH6", price=Decimal(22045), observed_at=evaluated_at
        ),
        evaluated_at=evaluated_at,
    )

    assert held is not None
    assert held.action is TmfPaperCycleAction.POSITION_MARKED
    assert held.performance_event is not None
    assert held.performance_event.stop_loss_price == Decimal(22060)
    assert held.journal.ledger.positions



@pytest.mark.parametrize(
    ("entry_code", "invalid_position", "invalid_slope", "exit_price"),
    (
        ("AU", "below", "falling", "22005"),
        ("BU", "above", "rising", "21995"),
    ),
)
def test_m15_ma20_invalidation_exits_open_paper_position_without_reversal(
    entry_code: str,
    invalid_position: str,
    invalid_slope: str,
    exit_price: str,
) -> None:
    session = LiveTmfPaperSimulation(config())
    session.process_evaluation(direction(entry_code), quote("22000"), evaluated_at=NOW)
    invalidated = decide_five_timeframe_paper_direction(
        tuple(
            MappedKamTimeframeState(timeframe, entry_code, entry_code[0], entry_code[1], ())
            for timeframe in ("1w", "1d", "60m", "15m", "5m")
        ),
        daily_ma60_position="above" if entry_code == "AU" else "below",
        m15_ma20_position=invalid_position,
        m15_ma20_direction=invalid_slope,
        m60_ma20_support="held" if entry_code == "AU" else "broken",
        m60_market_bias="bullish" if entry_code == "AU" else "bearish",
    )

    result = session.process_evaluation(
        invalidated,
        quote(exit_price, 1),
        evaluated_at=NOW + timedelta(minutes=1),
    )

    assert invalidated.direction == "HOLD"
    assert result.action is TmfPaperCycleAction.EXIT_FILLED
    assert result.performance_event is not None
    assert (
        result.performance_event.event_type
        is TmfPaperPerformanceEventType.M15_MA20_RULE_EXIT
    )
    assert result.reason_codes == ("M15_MA20_RULE_EXIT",)
    assert result.journal.open_entry is None
    assert result.journal.ledger.positions == ()
    assert result.direction == "HOLD"
