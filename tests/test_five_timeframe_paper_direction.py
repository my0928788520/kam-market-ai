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
    result = decide_five_timeframe_paper_direction(
        states("AU"),
        daily_ma60_position="above",
        m15_ma20_position="above",
        m15_ma20_direction="rising",
    )

    assert result.direction == "LONG"
    assert result.action == "PAPER_BUY"
    assert result.eligible is True
    assert result.live_order_allowed is False
    assert result.broker_connected is False


def test_all_confirmed_bearish_states_select_paper_short() -> None:
    result = decide_five_timeframe_paper_direction(
        states("BU"),
        daily_ma60_position="below",
        m15_ma20_position="below",
        m15_ma20_direction="falling",
    )

    assert result.direction == "SHORT"
    assert result.action == "PAPER_SELL"
    assert result.eligible is True
    assert result.live_order_allowed is False


def test_missing_ma_filters_fail_closed_even_when_five_timeframes_align() -> None:
    long_result = decide_five_timeframe_paper_direction(states("AU"))
    short_result = decide_five_timeframe_paper_direction(states("BU"))

    assert long_result.direction == "HOLD"
    assert long_result.reason_code == "DAILY_MA60_NOT_BULLISH"
    assert short_result.direction == "HOLD"
    assert short_result.reason_code == "DAILY_MA60_NOT_BEARISH"
    assert long_result.live_order_allowed is False
    assert short_result.live_order_allowed is False


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


def test_daily_ma60_filters_long_and_short_without_creating_opposite_orders() -> None:
    blocked_long = decide_five_timeframe_paper_direction(
        states("AU"), daily_ma60_position="below"
    )
    blocked_short = decide_five_timeframe_paper_direction(
        states("BU"), daily_ma60_position="above"
    )

    assert blocked_long.direction == "HOLD"
    assert blocked_long.reason_code == "DAILY_MA60_NOT_BULLISH"
    assert blocked_short.direction == "HOLD"
    assert blocked_short.reason_code == "DAILY_MA60_NOT_BEARISH"
    assert blocked_long.live_order_allowed is False
    assert blocked_short.live_order_allowed is False


@pytest.mark.parametrize(
    "warning",
    [
        "M15_ASCENDING_TRENDLINE_BROKEN_WEAKENING",
        "M15_DESCENDING_TRENDLINE_RESISTANCE_WEAKENING",
    ],
)
def test_m15_weakening_warning_blocks_fresh_long(warning: str) -> None:
    result = decide_five_timeframe_paper_direction(
        states("AU"),
        daily_ma60_position="above",
        trend_warning_codes=(warning,),
        m15_ma20_position="above",
        m15_ma20_direction="rising",
    )

    assert result.direction == "HOLD"
    assert result.reason_code == "M15_TREND_WEAKENING_WARNING"
    assert result.safe_payload()["trend_warning_codes"] == [warning]


@pytest.mark.parametrize(
    ("code", "position", "slope", "expected_direction"),
    [
        ("AU", "above", "rising", "LONG"),
        ("BU", "below", "falling", "SHORT"),
    ],
)
def test_m15_ma20_confirms_direction_and_keeps_one_contract_cap(
    code: str,
    position: str,
    slope: str,
    expected_direction: str,
) -> None:
    result = decide_five_timeframe_paper_direction(
        states(code),
        daily_ma60_position="above" if code == "AU" else "below",
        m15_ma20_position=position,
        m15_ma20_direction=slope,
    )

    assert result.direction == expected_direction
    assert result.eligible is True
    assert result.max_contracts == 1
    assert result.safe_payload()["max_contracts"] == 1
    assert result.safe_payload()["scale_in_allowed"] is False
    assert result.safe_payload()["averaging_down_allowed"] is False


@pytest.mark.parametrize(
    ("code", "position", "slope", "reason"),
    [
        ("AU", "below", "rising", "M15_MA20_LONG_TRIGGER_NOT_CONFIRMED"),
        ("AU", "above", "falling", "M15_MA20_LONG_TRIGGER_NOT_CONFIRMED"),
        ("BU", "above", "falling", "M15_MA20_SHORT_TRIGGER_NOT_CONFIRMED"),
        ("BU", "below", "rising", "M15_MA20_SHORT_TRIGGER_NOT_CONFIRMED"),
        ("AU", "insufficient", "insufficient", "M15_MA20_LONG_TRIGGER_NOT_CONFIRMED"),
    ],
)
def test_m15_ma20_mismatch_or_missing_data_holds(
    code: str,
    position: str,
    slope: str,
    reason: str,
) -> None:
    result = decide_five_timeframe_paper_direction(
        states(code),
        daily_ma60_position="above" if code == "AU" else "below",
        m15_ma20_position=position,
        m15_ma20_direction=slope,
    )

    assert result.direction == "HOLD"
    assert result.eligible is False
    assert result.reason_code == reason
    assert result.live_order_allowed is False
