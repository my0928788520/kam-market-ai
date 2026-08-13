import pytest

from kam_market_ai.live_read_only.five_timeframe_kam_rule_bridge import (
    evaluate_five_timeframe_kam_rules,
    map_analysis_frame_to_kam_state,
)


def frame(position="neutral", trend="neutral", structure="neutral", timing="confirmed", status="ready"):
    return {"position": position, "trend": trend, "structure": structure, "timing": timing, "status": status}


@pytest.mark.parametrize(
    ("values", "expected"),
    [
        (("bullish", "bullish", "supportive", "confirmed", "ready"), "AU"),
        (("bullish", "bullish", "supportive", "provisional", "provisional"), "AF"),
        (("bullish", "bullish", "supportive", "stale", "stale"), "AD"),
        (("neutral", "neutral", "neutral", "confirmed", "ready"), "NU"),
        (("neutral", "neutral", "neutral", "waiting", "provisional"), "NF"),
        (("neutral", "neutral", "neutral", "invalid", "invalid"), "ND"),
        (("bearish", "bearish", "bearish", "confirmed", "ready"), "BU"),
        (("bearish", "bearish", "bearish", "waiting", "provisional"), "BF"),
        (("bearish", "bearish", "bearish", "stale", "stale"), "BD"),
    ],
)
def test_mapping_covers_all_nine_canonical_states(values, expected):
    assert map_analysis_frame_to_kam_state("5m", frame(*values)).code == expected


def test_rule_bridge_emits_bullish_observation_but_never_an_order():
    analysis = {name: frame("bullish", "bullish", "supportive") for name in ("1w", "1d", "60m", "15m", "5m")}
    mapped, decision = evaluate_five_timeframe_kam_rules(analysis)
    assert [item.code for item in mapped] == ["AU"] * 5
    assert decision.direction == "偏多"
    assert decision.primary_next_action == "五週期偏多一致，等待人工確認"
    assert decision.action == "HOLD"
    assert decision.live_order_allowed is False


def test_bearish_and_conflicting_higher_timeframes_fail_closed():
    bearish = {name: frame("bearish", "bearish", "bearish") for name in ("1w", "1d", "60m", "15m", "5m")}
    _, bearish_decision = evaluate_five_timeframe_kam_rules(bearish)
    assert bearish_decision.direction == "偏空"
    assert bearish_decision.blockers == ("SHORT_STRATEGY_NOT_APPROVED",)
    assert bearish_decision.action == "HOLD"

    bearish["1w"] = frame("bullish", "bullish", "bullish")
    _, mixed = evaluate_five_timeframe_kam_rules(bearish)
    assert mixed.direction == "觀望"
    assert mixed.primary_next_action == "等待週線與日線方向一致"
