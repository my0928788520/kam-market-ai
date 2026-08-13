from __future__ import annotations

import pytest

from kam_market_ai.live_read_only.five_timeframe_decision_gate import (
    evaluate_live_five_timeframe_readiness,
)


def payload(**changes: object) -> dict[str, object]:
    value: dict[str, object] = {
        "status": "READY_VERIFIED_FIVE_TIMEFRAMES",
        "loaded_timeframes": ["5m", "15m", "60m", "1d", "1w"],
        "missing_timeframes": [],
        "market_data_only": True,
        "trading_enabled": False,
    }
    value.update(changes)
    return value


def test_ready_candles_remain_blocked_until_real_state_classifier_exists() -> None:
    result = evaluate_live_five_timeframe_readiness(payload())

    assert result.decision_status == "BLOCKED"
    assert result.action == "HOLD"
    assert result.blockers == ("TIMEFRAME_STATE_CLASSIFICATION_REQUIRED",)
    assert result.live_order_allowed is False


def test_incomplete_candles_fail_closed_before_classification() -> None:
    result = evaluate_live_five_timeframe_readiness(payload(
        status="ATTESTATION_REQUIRED",
        loaded_timeframes=["5m", "15m", "60m"],
        missing_timeframes=["1d", "1w"],
    ))

    assert result.blockers == ("FIVE_TIMEFRAME_DATA_INCOMPLETE",)
    assert result.action == "HOLD"


@pytest.mark.parametrize(
    "changes",
    [
        {"market_data_only": False},
        {"trading_enabled": True},
    ],
)
def test_gate_rejects_unsafe_payloads(changes: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        evaluate_live_five_timeframe_readiness(payload(**changes))
