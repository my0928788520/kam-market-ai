from datetime import UTC, datetime, time, timedelta, timezone
from decimal import Decimal
import ast
import inspect
import pytest

from kam_market_ai.paper_trading import safety
from kam_market_ai.paper_trading.contracts import PaperTradingAccountSnapshot, PaperTradingOrderRequest, PaperTradingPosition, PaperTradingRiskLimits, PaperTradingSafetyState, PaperTradingSide


NOW = datetime(2026, 8, 13, 2, tzinfo=UTC)


def request(**changes):
    base = {"idempotency_key": "key-1", "instrument": "MTX", "side": PaperTradingSide.BUY, "quantity": Decimal("1"), "price": Decimal("100"), "created_at": NOW}
    base.update(changes); return PaperTradingOrderRequest(**base)


def state(**changes):
    limits = PaperTradingRiskLimits(Decimal("2"), Decimal("500"), Decimal("100"), 1, ("MTX",), (NOW.weekday(),), time(1), time(5))
    account = PaperTradingAccountSnapshot((), Decimal("0"), NOW)
    base = {"paper_trading_enabled": True, "emergency_stop": False, "used_idempotency_keys": (), "account_snapshot": account, "risk_limits": limits}
    base.update(changes); return PaperTradingSafetyState(**base)


def test_default_disabled_and_emergency_stop_reject():
    assert "PAPER_TRADING_DISABLED" in safety.evaluate_paper_trading_order(request(), PaperTradingSafetyState()).reason_codes
    assert "EMERGENCY_STOP" in safety.evaluate_paper_trading_order(request(), state(emergency_stop=True)).reason_codes


def test_duplicate_quantity_notional_loss_instrument_and_position_limits_reject():
    assert "DUPLICATE_IDEMPOTENCY_KEY" in safety.evaluate_paper_trading_order(request(), state(used_idempotency_keys=("key-1",))).reason_codes
    assert "MAX_ORDER_QUANTITY_EXCEEDED" in safety.evaluate_paper_trading_order(request(quantity=Decimal("3")), state()).reason_codes
    assert "MAX_NOTIONAL_EXCEEDED" in safety.evaluate_paper_trading_order(request(price=Decimal("600")), state()).reason_codes
    loss = PaperTradingAccountSnapshot((), Decimal("-100"), NOW)
    assert "MAX_DAILY_LOSS_EXCEEDED" in safety.evaluate_paper_trading_order(request(), state(account_snapshot=loss)).reason_codes
    assert "INSTRUMENT_NOT_ALLOWED" in safety.evaluate_paper_trading_order(request(instrument="OTHER"), state()).reason_codes
    occupied = PaperTradingAccountSnapshot((PaperTradingPosition("OTHER", Decimal("1"), Decimal("1"), Decimal("0"), NOW),), Decimal("0"), NOW)
    assert "MAX_OPEN_POSITIONS_EXCEEDED" in safety.evaluate_paper_trading_order(request(), state(account_snapshot=occupied)).reason_codes


def test_invalid_version_timestamp_session_and_success_are_deterministic():
    assert "INVALID_VERSION" in safety.evaluate_paper_trading_order(request(request_version="9"), state()).reason_codes
    with pytest.raises(ValueError, match="UTC"):
        request(created_at=NOW.astimezone(timezone(timedelta(hours=8))))
    outside = request(created_at=NOW.replace(hour=6))
    assert "TRADING_SESSION_NOT_ALLOWED" in safety.evaluate_paper_trading_order(outside, state()).reason_codes
    accepted = safety.evaluate_paper_trading_order(request(), state())
    assert accepted.state.value == "accepted" and accepted.result_hash == safety.evaluate_paper_trading_order(request(), state()).result_hash
    assert safety.build_paper_trading_audit_event(accepted).event_hash == safety.build_paper_trading_audit_event(accepted).event_hash


def test_safety_has_no_network_or_sdk_dependency_and_no_sensitive_fields():
    source = inspect.getsource(safety).lower()
    imported = {
        alias.name.split(".")[0]
        for node in ast.walk(ast.parse(source))
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in (node.names if isinstance(node, ast.Import) else ())
    }
    assert not {"requests", "urllib", "socket", "websocket", "fubon"}.intersection(imported)
    fields = set(PaperTradingOrderRequest.__dataclass_fields__)
    assert not {"password", "token", "api_key", "secret"}.intersection(fields)


def test_tmf_is_permanently_limited_to_one_net_contract() -> None:
    tmf_limits = PaperTradingRiskLimits(
        Decimal("10"),
        Decimal("1000000"),
        Decimal("100"),
        1,
        ("TMFH6",),
        (NOW.weekday(),),
        time(1),
        time(5),
    )
    empty = PaperTradingAccountSnapshot((), Decimal("0"), NOW)
    tmf_state = state(account_snapshot=empty, risk_limits=tmf_limits)

    two_contracts = request(instrument="TMFH6", quantity=Decimal("2"))
    result = safety.evaluate_paper_trading_order(two_contracts, tmf_state)
    assert "ONE_MICRO_TAIWAN_CONTRACT_LIMIT" in result.reason_codes

    existing_long = PaperTradingAccountSnapshot(
        (PaperTradingPosition("TMFH6", Decimal("1"), Decimal("100"), Decimal("0"), NOW),),
        Decimal("0"),
        NOW,
    )
    add_long = safety.evaluate_paper_trading_order(
        request(instrument="TMFH6"),
        state(account_snapshot=existing_long, risk_limits=tmf_limits),
    )
    assert "ONE_MICRO_TAIWAN_CONTRACT_LIMIT" in add_long.reason_codes

    close_long = safety.evaluate_paper_trading_order(
        request(instrument="TMFH6", side=PaperTradingSide.SELL),
        state(account_snapshot=existing_long, risk_limits=tmf_limits),
    )
    assert close_long.state.value == "accepted"
