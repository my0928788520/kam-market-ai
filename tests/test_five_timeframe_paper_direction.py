import pytest

from kam_market_ai.live_read_only.five_timeframe_kam_rule_bridge import (
    MappedKamTimeframeState,
)
from kam_market_ai.paper_trading.five_timeframe_paper_direction import (
    decide_five_timeframe_paper_direction,
)


def states(code: str) -> tuple[MappedKamTimeframeState, ...]:
    return tuple(
        MappedKamTimeframeState(timeframe, code, code[0], code[1], ())
        for timeframe in ("1w", "1d", "60m", "15m", "5m")
    )


def test_all_confirmed_bullish_states_select_paper_long() -> None:
    result = decide_five_timeframe_paper_direction(states("AU"))

    assert result.direction == "LONG"
    assert result.action == "PAPER_BUY"
    assert result.eligible is True
    assert result.live_order_allowed is False
    assert result.broker_connected is False


def test_all_confirmed_bearish_states_select_paper_short() -> None:
    result = decide_five_timeframe_paper_direction(states("BU"))

    assert result.direction == "SHORT"
    assert result.action == "PAPER_SELL"
    assert result.eligible is True
    assert result.live_order_allowed is False


@pytest.mark.parametrize("code", ["AF", "AD", "NU", "NF", "ND", "BF", "BD"])
def test_forming_neutral_or_degraded_states_hold(code: str) -> None:
    result = decide_five_timeframe_paper_direction(states(code))

    assert result.direction == "HOLD"
    assert result.action == "NO_PAPER_ORDER"
    assert result.eligible is False


def test_mixed_direction_holds() -> None:
    mixed = list(states("AU"))
    mixed[-1] = MappedKamTimeframeState("5m", "BU", "B", "U", ())

    assert decide_five_timeframe_paper_direction(tuple(mixed)).direction == "HOLD"


def test_gate_requires_exactly_five_mapped_states() -> None:
    with pytest.raises(TypeError, match="five mapped"):
        decide_five_timeframe_paper_direction(states("AU")[:4])
