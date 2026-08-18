import pytest

from kam_market_ai.live_read_only.five_timeframe_kam_rule_bridge import (
    MappedKamTimeframeState,
)
from kam_market_ai.paper_trading.five_timeframe_paper_direction import (
    decide_five_timeframe_paper_direction,
)


def states(code: str) -> tuple[MappedKamTimeframeState, ...]:
    return tuple(MappedKamTimeframeState(timeframe, code, code[0], code[1], ()) for timeframe in ("1w", "1d", "60m", "15m", "5m"))


def test_m60_bullish_location_and_m15_trigger_select_one_contract_paper_long() -> None:
    result = decide_five_timeframe_paper_direction(
        states("ND"), daily_ma60_position="below",
        m15_ma20_position="above", m15_ma20_direction="rising",
        m60_ma20_support="retest_held", m60_market_bias="bullish",
    )
    assert (result.direction, result.action, result.reason_code) == (
        "LONG", "PAPER_BUY", "M60_BULLISH_M15_LONG_TRIGGER"
    )
    assert result.eligible is True
    assert result.max_contracts == 1
    assert result.live_order_allowed is False
    assert result.broker_connected is False
    assert result.safe_payload()["scale_in_allowed"] is False
    assert result.safe_payload()["averaging_down_allowed"] is False


def test_m60_bearish_location_and_m15_trigger_select_one_contract_paper_short() -> None:
    result = decide_five_timeframe_paper_direction(
        states("ND"), daily_ma60_position="above",
        m15_ma20_position="below", m15_ma20_direction="falling",
        m60_ma20_support="broken", m60_market_bias="bearish",
    )
    assert (result.direction, result.action, result.reason_code) == (
        "SHORT", "PAPER_SELL", "M60_BEARISH_M15_SHORT_TRIGGER"
    )
    assert result.eligible is True
    assert result.max_contracts == 1
    assert result.live_order_allowed is False


@pytest.mark.parametrize("code", ["AU", "AF", "ND", "BU", "BD"])
def test_five_timeframe_alignment_no_longer_vetoes_valid_m60_m15_setup(code: str) -> None:
    result = decide_five_timeframe_paper_direction(
        states(code), m15_ma20_position="above", m15_ma20_direction="rising",
        m60_ma20_support="held", m60_market_bias="bullish",
    )
    assert result.direction == "LONG"
    assert result.eligible is True
    assert result.timeframe_states == (code,) * 5


@pytest.mark.parametrize("daily_position", [None, "above", "below", "insufficient"])
def test_daily_ma60_is_context_not_an_entry_veto(daily_position: str | None) -> None:
    result = decide_five_timeframe_paper_direction(
        states("ND"), daily_ma60_position=daily_position,
        m15_ma20_position="below", m15_ma20_direction="falling",
        m60_ma20_support="broken", m60_market_bias="bearish",
    )
    assert result.direction == "SHORT"
    assert result.daily_ma60_position == daily_position


def test_trend_warning_is_context_without_overriding_trigger() -> None:
    warning = "M15_ASCENDING_TRENDLINE_BROKEN_WEAKENING"
    result = decide_five_timeframe_paper_direction(
        states("ND"), trend_warning_codes=(warning,),
        m15_ma20_position="above", m15_ma20_direction="rising",
        m60_ma20_support="held", m60_market_bias="bullish",
    )
    assert result.direction == "LONG"
    assert result.safe_payload()["trend_warning_codes"] == [warning]


@pytest.mark.parametrize("position,slope", [("below", "rising"), ("above", "falling"), ("insufficient", "insufficient")])
def test_m15_long_trigger_mismatch_holds(position: str, slope: str) -> None:
    result = decide_five_timeframe_paper_direction(
        states("AU"), m15_ma20_position=position, m15_ma20_direction=slope,
        m60_ma20_support="held", m60_market_bias="bullish",
    )
    assert result.direction == "HOLD"
    assert result.reason_code == "M15_MA20_LONG_TRIGGER_NOT_CONFIRMED"
    assert result.eligible is False


@pytest.mark.parametrize("position,slope", [("above", "falling"), ("below", "rising"), ("equal", "flat")])
def test_m15_short_trigger_mismatch_holds(position: str, slope: str) -> None:
    result = decide_five_timeframe_paper_direction(
        states("BU"), m15_ma20_position=position, m15_ma20_direction=slope,
        m60_ma20_support="broken", m60_market_bias="bearish",
    )
    assert result.direction == "HOLD"
    assert result.reason_code == "M15_MA20_SHORT_TRIGGER_NOT_CONFIRMED"


def test_m60_location_is_required_and_fails_closed_when_insufficient() -> None:
    result = decide_five_timeframe_paper_direction(
        states("AU"), m15_ma20_position="above", m15_ma20_direction="rising",
        m60_ma20_support="insufficient", m60_market_bias="insufficient",
    )
    assert result.direction == "HOLD"
    assert result.reason_code == "M60_LOCATION_INSUFFICIENT"
    assert result.live_order_allowed is False


def test_inconsistent_m60_location_holds_without_guessing_direction() -> None:
    result = decide_five_timeframe_paper_direction(
        states("AU"), m15_ma20_position="above", m15_ma20_direction="rising",
        m60_ma20_support="broken", m60_market_bias="bullish",
    )
    assert result.direction == "HOLD"
    assert result.reason_code == "M60_LOCATION_NOT_DIRECTIONAL"


def test_gate_still_requires_exactly_five_mapped_states_for_diagnostics() -> None:
    with pytest.raises(TypeError, match="five mapped"):
        decide_five_timeframe_paper_direction(states("AU")[:4])


def test_normalized_inputs_are_still_validated() -> None:
    with pytest.raises(ValueError, match="m60_market_bias"):
        decide_five_timeframe_paper_direction(states("AU"), m60_market_bias="up")
