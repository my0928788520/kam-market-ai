from dataclasses import replace
from datetime import UTC, datetime, time
from decimal import Decimal

import pytest

from kam_market_ai.paper_trading.contracts import (
    PAPER_TRADING_CONTRACT_VERSION, PaperTradingAccountSnapshot, PaperTradingAuditEvent,
    PaperTradingFill, PaperTradingOrderRequest, PaperTradingOrderState, PaperTradingPosition,
    PaperTradingRiskLimits, PaperTradingSafetyState, PaperTradingSide,
)


NOW = datetime(2026, 8, 13, 2, tzinfo=UTC)


def request(): return PaperTradingOrderRequest("request-1", "MTX", PaperTradingSide.BUY, Decimal("1"), Decimal("100"), NOW)
def position(): return PaperTradingPosition("MTX", Decimal("1"), Decimal("100"), Decimal("0"), NOW)
def limits(): return PaperTradingRiskLimits(Decimal("2"), Decimal("1000"), Decimal("100"), 2, ("MTX",), (2,), time(1), time(5))


def test_contracts_are_immutable_and_hashes_are_deterministic():
    first = request(); second = request()
    assert first.request_hash == second.request_hash
    with pytest.raises(Exception): first.price = Decimal("101")  # type: ignore[misc]
    fill = PaperTradingFill("fill-1", "request-1", "MTX", PaperTradingSide.BUY, Decimal("1"), Decimal("100"), Decimal("0"), NOW)
    assert fill.fill_hash == PaperTradingFill("fill-1", "request-1", "MTX", PaperTradingSide.BUY, Decimal("1"), Decimal("100"), Decimal("0"), NOW).fill_hash


def test_account_positions_limits_and_utc_timestamps_fail_closed():
    assert PaperTradingAccountSnapshot((position(),), Decimal("0"), NOW).positions[0].instrument == "MTX"
    with pytest.raises(ValueError, match="unique"):
        PaperTradingAccountSnapshot((position(), position()), Decimal("0"), NOW)
    with pytest.raises(ValueError, match="UTC"):
        replace(request(), created_at=NOW.replace(tzinfo=None))
    with pytest.raises(ValueError, match="canonical"):
        PaperTradingRiskLimits(Decimal("1"), Decimal("1"), Decimal("1"), 1, ("MTX", "MTX"), (2,), time(1), time(2))


def test_isolation_flags_are_fixed_false_or_true():
    state = PaperTradingSafetyState(account_snapshot=PaperTradingAccountSnapshot((), Decimal("0"), NOW), risk_limits=limits())
    assert request().dry_run is True and request().live_order_allowed is False and request().broker_connected is False and request().account_credentials_allowed is False
    assert state.dry_run is True and state.live_order_allowed is False and state.broker_connected is False and state.account_credentials_allowed is False
    with pytest.raises(ValueError): replace(request(), live_order_allowed=True)


def test_audit_event_is_deterministic_and_state_machine_has_no_cancel_transition():
    event = PaperTradingAuditEvent("order_rejected", request().request_hash, "result", NOW, ("A",))
    assert event.event_hash == PaperTradingAuditEvent("order_rejected", request().request_hash, "result", NOW, ("A",)).event_hash
    assert not {"cancelled", "modified"}.intersection(state.value for state in PaperTradingOrderState)
    assert PAPER_TRADING_CONTRACT_VERSION == "0.1"
