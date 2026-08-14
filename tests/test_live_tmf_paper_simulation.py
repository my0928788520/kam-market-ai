from datetime import UTC, datetime, timedelta
from decimal import Decimal
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
    LiveTmfPaperSimulation,
    TmfPaperCycleAction,
    TmfPaperJournalStore,
    TmfPaperPerformanceEventType,
    TmfPaperQuote,
    TmfPaperSimulationConfig,
)

NOW = datetime(2026, 8, 14, 5, 0, tzinfo=UTC)


def direction(code: str):
    states = tuple(
        MappedKamTimeframeState(timeframe, code, code[0], code[1], ())
        for timeframe in ("1w", "1d", "60m", "15m", "5m")
    )
    return decide_five_timeframe_paper_direction(states)


def quote(price: str, minute: int = 0) -> TmfPaperQuote:
    return TmfPaperQuote(
        "TMFH6",
        Decimal(price),
        NOW + timedelta(minutes=minute),
        f"{minute + int(Decimal(price)):064x}"[-64:],
    )


def config(*, enabled: bool = True, confirmed: bool = True) -> TmfPaperSimulationConfig:
    return TmfPaperSimulationConfig(
        instrument="TMFH6",
        paper_trading_enabled=enabled,
        manual_approval_granted=confirmed,
    )


def enter(session: LiveTmfPaperSimulation):
    return session.process_evaluation(direction("AU"), quote("22000"), evaluated_at=NOW)


def test_default_session_holds_without_kam_buy_condition() -> None:
    session = LiveTmfPaperSimulation(config())

    result = session.process_evaluation(direction("AF"), quote("22000"), evaluated_at=NOW)

    assert result.action is TmfPaperCycleAction.HOLD
    assert result.reason_codes == ("KAM_BUY_CONDITION_NOT_MET",)
    assert result.journal.events == ()


def test_short_direction_never_opens_a_buy() -> None:
    session = LiveTmfPaperSimulation(config())

    result = session.process_evaluation(direction("BU"), quote("22000"), evaluated_at=NOW)

    assert result.action is TmfPaperCycleAction.HOLD
    assert result.reason_codes == ("PAPER_SHORT_NOT_ENABLED",)
    assert not result.journal.ledger.positions


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


def test_confirmed_natural_buy_records_fill_protection_position_and_cash() -> None:
    session = LiveTmfPaperSimulation(config())

    result = enter(session)

    assert result.action is TmfPaperCycleAction.ENTRY_FILLED
    assert result.fill_hashes
    assert len(result.journal.ledger.positions) == 1
    assert result.journal.ledger.positions[0].average_price == Decimal(22000)
    assert result.journal.ledger.cash_balance == Decimal(978000)
    event = result.performance_event
    assert event is not None
    assert event.event_type is TmfPaperPerformanceEventType.ENTRY
    assert event.stop_loss_price == Decimal(21980)
    assert event.take_profit_price == Decimal(22040)
    assert event.point_value == Decimal(10)


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


def test_take_profit_quote_closes_position_and_records_realized_gain() -> None:
    session = LiveTmfPaperSimulation(config())
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

    assert restored.journal_hash == session.journal.journal_hash
    assert restored.ledger.ledger_hash == session.journal.ledger.ledger_hash
    assert len(restored.events) == 2


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
