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
    assert result.journal.ledger.cash_balance == Decimal(1000420)
    assert result.journal.ledger.cash_entries[-1].cash_delta == Decimal(35470)


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
