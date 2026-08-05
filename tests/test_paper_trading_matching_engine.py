from datetime import UTC, datetime, time
from decimal import Decimal

import pytest

from kam_market_ai.paper_trading.contracts import (
    PaperTradingAccountSnapshot,
    PaperTradingOrderRequest,
    PaperTradingPosition,
    PaperTradingRiskLimits,
    PaperTradingSafetyState,
    PaperTradingSide,
)
from kam_market_ai.paper_trading.ledger import PaperTradingLedger
from kam_market_ai.paper_trading.matching_engine import (
    InMemoryPaperOrderBook,
    OfflineMarketSnapshot,
    PaperTradingMatchState,
    PaperTradingOrderType,
    cancel_paper_trading_order,
    match_paper_trading_order,
)


NOW = datetime(2026, 8, 13, 2, 0, tzinfo=UTC)


def _request(key: str, side: PaperTradingSide = PaperTradingSide.BUY, *, quantity: str = "1", price: str = "101") -> PaperTradingOrderRequest:
    return PaperTradingOrderRequest(key, "TEST", side, Decimal(quantity), Decimal(price), NOW)


def _book(*, available: str = "5") -> InMemoryPaperOrderBook:
    return InMemoryPaperOrderBook((OfflineMarketSnapshot("TEST", Decimal("99"), Decimal("101"), Decimal(available), Decimal(available), NOW),))


def _state(*, emergency: bool = False, positions: tuple[PaperTradingPosition, ...] = ()) -> PaperTradingSafetyState:
    account = PaperTradingAccountSnapshot(positions, Decimal("0"), NOW)
    limits = PaperTradingRiskLimits(Decimal("10"), Decimal("10000"), Decimal("500"), 3, ("TEST",), (NOW.weekday(),), time(0), time(23, 59))
    return PaperTradingSafetyState(True, emergency, (), account, limits)


def test_market_buy_and_sell_full_fill_update_ledgers_and_audit() -> None:
    buy = match_paper_trading_order(_request("buy"), PaperTradingOrderType.MARKET, _book(), PaperTradingLedger(Decimal("1000")), _state(), fee_rate=Decimal("0.01"))
    assert buy.state is PaperTradingMatchState.FILLED
    assert buy.fills[0].price == Decimal("101")
    assert buy.fills[0].fees == Decimal("1.01")
    assert buy.ledger.cash_balance == Decimal("897.99")
    assert buy.audit_event.event_type == "order_filled"

    sell_position = PaperTradingPosition("TEST", Decimal("1"), Decimal("101"), Decimal("0"), NOW)
    sell = match_paper_trading_order(_request("sell", PaperTradingSide.SELL, price="99"), PaperTradingOrderType.MARKET, _book(), buy.ledger, _state(positions=(sell_position,)))
    assert sell.state is PaperTradingMatchState.FILLED
    assert sell.fills[0].price == Decimal("99")
    assert sell.ledger.positions == ()


def test_limit_no_fill_full_fill_partial_fill_and_local_cancel_are_deterministic() -> None:
    no_fill = match_paper_trading_order(_request("open", price="100"), PaperTradingOrderType.LIMIT, _book(), PaperTradingLedger(Decimal("1000")), _state())
    assert no_fill.state is PaperTradingMatchState.OPEN
    assert no_fill.fills == ()

    full = match_paper_trading_order(_request("full"), PaperTradingOrderType.LIMIT, _book(), PaperTradingLedger(Decimal("1000")), _state())
    assert full.state is PaperTradingMatchState.FILLED

    partial = match_paper_trading_order(_request("partial", quantity="3"), PaperTradingOrderType.MARKET, _book(available="2"), PaperTradingLedger(Decimal("1000")), _state())
    assert partial.state is PaperTradingMatchState.PARTIALLY_FILLED
    assert partial.fills[0].quantity == Decimal("2")

    cancelled = cancel_paper_trading_order(_request("cancel"), PaperTradingLedger(Decimal("1000")))
    assert cancelled.state is PaperTradingMatchState.CANCELLED


def test_duplicate_insufficient_cash_position_and_emergency_stop_reject_without_mutation() -> None:
    ledger = PaperTradingLedger(Decimal("1000"))
    first = match_paper_trading_order(_request("dup"), PaperTradingOrderType.MARKET, _book(), ledger, _state())
    duplicate = match_paper_trading_order(_request("dup"), PaperTradingOrderType.MARKET, _book(), first.ledger, _state())
    assert duplicate.state is PaperTradingMatchState.REJECTED
    assert "DUPLICATE_IDEMPOTENCY_KEY" in duplicate.reason_codes

    poor = PaperTradingLedger(Decimal("1"))
    cash_rejected = match_paper_trading_order(_request("cash"), PaperTradingOrderType.MARKET, _book(), poor, _state())
    assert cash_rejected.state is PaperTradingMatchState.REJECTED
    assert cash_rejected.ledger is poor

    sell_rejected = match_paper_trading_order(_request("position", PaperTradingSide.SELL, price="99"), PaperTradingOrderType.MARKET, _book(), ledger, _state())
    assert sell_rejected.state is PaperTradingMatchState.REJECTED
    assert sell_rejected.ledger is ledger

    stopped = match_paper_trading_order(_request("stop"), PaperTradingOrderType.MARKET, _book(), ledger, _state(emergency=True))
    assert stopped.state is PaperTradingMatchState.REJECTED
    assert "EMERGENCY_STOP" in stopped.reason_codes


def test_matching_is_deterministic_immutable_and_has_no_network_or_credentials() -> None:
    request = _request("stable")
    first = match_paper_trading_order(request, PaperTradingOrderType.MARKET, _book(), PaperTradingLedger(Decimal("1000")), _state())
    second = match_paper_trading_order(request, PaperTradingOrderType.MARKET, _book(), PaperTradingLedger(Decimal("1000")), _state())
    assert first.result_hash == second.result_hash
    assert first.fills[0].fill_id == second.fills[0].fill_id
    assert first.audit_event.fill_hashes == tuple(sorted(first.audit_event.fill_hashes))
    with pytest.raises(Exception):
        first.state = PaperTradingMatchState.REJECTED  # type: ignore[misc]
    payload = first.canonical_payload()
    assert payload["dry_run"] is True
    assert payload["live_order_allowed"] is False
    assert payload["broker_connected"] is False
    assert payload["account_credentials_allowed"] is False

    import kam_market_ai.paper_trading.matching_engine as module
    source = open(module.__file__, encoding="utf-8").read().lower()
    for forbidden in ("import requests", "import urllib", "import websocket", "import fubon", "import fugle"):
        assert forbidden not in source
