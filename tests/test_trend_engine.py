from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from kam_market_ai.analysis.position_engine import DataStatus, PositionTimeframe
from kam_market_ai.analysis.trend_engine import (
    BreakPriceSource,
    RelationToTrendline,
    ToleranceMode,
    TrendDuplicateTimestampPolicy,
    TrendEngineConfig,
    TrendState,
    TrendlineType,
    evaluate_all_trendlines,
    evaluate_trendline,
)
from kam_market_ai.models import Candle, Instrument


NOW = datetime(2026, 7, 31, 10, tzinfo=UTC)


def series(highs: list[float], lows: list[float], closes: list[float] | None = None, *, start: datetime = NOW) -> list[Candle]:
    closes = closes or [(high + low) / 2 for high, low in zip(highs, lows)]
    length = len(highs)
    return [
        Candle(Instrument.MTX, start - timedelta(minutes=length - index + 1), start - timedelta(minutes=length - index),
               (high + low) / 2, high, low, close, 1)
        for index, (high, low, close) in enumerate(zip(highs, lows, closes))
    ]


def config(**changes: object) -> TrendEngineConfig:
    base = TrendEngineConfig.provisional()
    mapping = {item: 20 for item in PositionTimeframe}
    days = {item: timedelta(days=365) for item in PositionTimeframe}
    return TrendEngineConfig(
        lookback_by_timeframe=changes.get("lookback_by_timeframe", mapping),
        minimum_closed_candles_by_timeframe=changes.get("minimum_closed_candles_by_timeframe", {item: 5 for item in PositionTimeframe}),
        pivot_left_window_by_timeframe=changes.get("pivot_left_window_by_timeframe", {item: 1 for item in PositionTimeframe}),
        pivot_right_window_by_timeframe=changes.get("pivot_right_window_by_timeframe", {item: 1 for item in PositionTimeframe}),
        minimum_anchor_separation_by_timeframe=changes.get("minimum_anchor_separation_by_timeframe", {item: 2 for item in PositionTimeframe}),
        maximum_anchor_age_by_timeframe=changes.get("maximum_anchor_age_by_timeframe", days),
        tolerance_value_by_timeframe=changes.get("tolerance_value_by_timeframe", {item: Decimal("0.1") for item in PositionTimeframe}),
        break_confirmation_bars_by_timeframe=changes.get("break_confirmation_bars_by_timeframe", {item: 2 for item in PositionTimeframe}),
        retest_max_bars_by_timeframe=changes.get("retest_max_bars_by_timeframe", {item: 4 for item in PositionTimeframe}),
        stale_after_by_timeframe=changes.get("stale_after_by_timeframe", {item: timedelta(days=2) for item in PositionTimeframe}),
        plateau_policy=changes.get("plateau_policy", base.plateau_policy),
        tolerance_mode=changes.get("tolerance_mode", ToleranceMode.FIXED_POINTS),
        break_price_source=changes.get("break_price_source", BreakPriceSource.CLOSE),
        maximum_violation_count=changes.get("maximum_violation_count", 10),
        minimum_touch_count=changes.get("minimum_touch_count", 0),
        allow_sort_input=changes.get("allow_sort_input", True),
        duplicate_timestamp_policy=changes.get("duplicate_timestamp_policy", base.duplicate_timestamp_policy),
        ambiguity_score_gap=changes.get("ambiguity_score_gap", Decimal("0.000001")),
        minimum_absolute_slope=changes.get("minimum_absolute_slope", Decimal("0.0000001")),
        maximum_absolute_slope=changes.get("maximum_absolute_slope", Decimal("1000")),
    )


ASC_HIGHS = [14, 13, 12, 13, 14, 15, 14, 13, 14]
ASC_LOWS = [10, 9, 8, 9, 10, 11, 10, 9, 10]
DESC_HIGHS = [20, 21, 22, 21, 20, 19, 20, 21, 20]
DESC_LOWS = [16, 17, 18, 17, 16, 15, 16, 17, 16]


def evaluate(candles: list[Candle], price: object, **changes: object):
    return evaluate_trendline(PositionTimeframe.M15, candles, price, NOW, config(**changes))


def test_ascending_line_projection_above_and_touching() -> None:
    candles = series(ASC_HIGHS, ASC_LOWS)
    above = evaluate(candles, 11)
    touching = evaluate(candles, above.projected_value_at_evaluated_at)
    assert above.active_trendline_type is TrendlineType.ASCENDING
    assert above.slope_per_second and above.slope_per_second > 0
    assert above.relation_to_trendline is RelationToTrendline.ABOVE
    assert touching.relation_to_trendline is RelationToTrendline.TOUCHING


def test_ascending_rejects_non_higher_low_and_too_close_anchors() -> None:
    no_higher_low = series([14, 13, 12, 13, 14, 15, 14, 13, 14], [10, 9, 8, 9, 10, 11, 10, 8, 10])
    too_close = evaluate(series(ASC_HIGHS, ASC_LOWS), 11, minimum_anchor_separation_by_timeframe={item: 10 for item in PositionTimeframe})
    assert evaluate(no_higher_low, 10).trend_state is TrendState.NO_VALID_TRENDLINE
    assert too_close.trend_state is TrendState.NO_VALID_TRENDLINE


def test_descending_line_below_and_touching() -> None:
    candles = series(DESC_HIGHS, DESC_LOWS)
    below = evaluate(candles, 19)
    touching = evaluate(candles, below.projected_value_at_evaluated_at)
    assert below.active_trendline_type is TrendlineType.DESCENDING
    assert below.slope_per_second and below.slope_per_second < 0
    assert below.relation_to_trendline is RelationToTrendline.BELOW
    assert touching.relation_to_trendline is RelationToTrendline.TOUCHING


def test_descending_rejects_non_lower_high_and_zero_slope() -> None:
    no_lower_high = series([20, 21, 22, 21, 20, 19, 20, 22, 20], DESC_LOWS)
    assert evaluate(no_lower_high, 19).trend_state is TrendState.NO_VALID_TRENDLINE


def test_confirmed_break_and_unclosed_price_cannot_confirm_break() -> None:
    highs = [14, 13, 12, 13, 14, 15, 14, 13, 12, 11, 10]
    lows = ASC_LOWS + [7, 6]
    broken = evaluate(series(highs, lows, closes=[12, 11, 10, 11, 12, 13, 12, 11, 12, 7, 6]), 6)
    unclosed = evaluate(series(ASC_HIGHS, ASC_LOWS), 1)
    assert broken.relation_to_trendline is RelationToTrendline.BREAKDOWN_DOWN
    assert broken.valid is False and broken.trend_state is TrendState.ASCENDING_BROKEN
    assert unclosed.relation_to_trendline is RelationToTrendline.BELOW


def test_break_retest_and_rejection_event_order() -> None:
    highs = [14, 13, 12, 13, 14, 15, 14, 13, 12, 11, 10, 11]
    lows = ASC_LOWS + [7, 6, 9.8]
    closes = [12, 11, 10, 11, 12, 13, 12, 11, 12, 7, 6, 9.8]
    candles = series(highs, lows, closes)
    retest = evaluate(candles, 10)
    rejection = evaluate(candles, 6)
    assert retest.relation_to_trendline is RelationToTrendline.RETEST
    assert rejection.relation_to_trendline is RelationToTrendline.REJECTION


def test_touch_count_and_violation_limit() -> None:
    highs = [14, 13, 12, 13, 14, 15, 14, 13, 12]
    touch_lows = [10, 9, 8, 9, 10, 9, 10, 11, 10.33]
    touched = evaluate(series(highs, touch_lows), 11, tolerance_value_by_timeframe={item: Decimal("0.5") for item in PositionTimeframe})
    invalid_lows = [10, 9, 8, 9, 10, 9, 10, 11, 7]
    invalid = evaluate(series(highs, invalid_lows, closes=[12, 11, 10, 11, 12, 12, 12, 12, 7]), 11, maximum_violation_count=0, break_confirmation_bars_by_timeframe={item: 3 for item in PositionTimeframe})
    assert touched.touch_count >= 1
    assert invalid.valid is False or invalid.trend_state is not TrendState.ASCENDING_SUPPORTED


def test_candidate_ambiguity_and_selection() -> None:
    highs = [14, 13, 12, 13, 14, 15, 14, 13, 14, 15, 16, 15, 14, 15, 16]
    lows = [10, 9, 8, 9, 10, 11, 10, 9, 10, 11, 12, 11, 10, 11, 12]
    candles = series(highs, lows)
    ambiguous = evaluate(candles, 13, ambiguity_score_gap=Decimal("999"))
    selected = evaluate(candles, 13, ambiguity_score_gap=Decimal("0"))
    assert ambiguous.trend_state is TrendState.AMBIGUOUS
    assert selected.active_trendline_type is TrendlineType.ASCENDING


def test_stale_invalid_timezone_overlap_duplicate_and_out_of_order_fail_closed() -> None:
    candles = series(ASC_HIGHS, ASC_LOWS, start=NOW - timedelta(days=5))
    stale = evaluate(candles, 11, stale_after_by_timeframe={item: timedelta(hours=1) for item in PositionTimeframe})
    duplicate = series(ASC_HIGHS, ASC_LOWS); duplicate[1] = replace(duplicate[1], start=duplicate[0].start, end=duplicate[0].end)
    unordered = [duplicate[2], duplicate[0], duplicate[1], *duplicate[3:]]
    assert stale.data_status is DataStatus.STALE
    assert evaluate(duplicate, 11).data_status is DataStatus.INVALID
    sorted_result = evaluate(unordered, 11, duplicate_timestamp_policy=TrendDuplicateTimestampPolicy.KEEP_LAST)
    assert "candles_sorted_by_end" in sorted_result.warnings


def test_unclosed_candle_never_becomes_anchor_or_confirms_break() -> None:
    candles = series(ASC_HIGHS, ASC_LOWS)
    future = Candle(Instrument.MTX, NOW, NOW + timedelta(minutes=1), 10, 999, 1, 1, 1)
    result = evaluate(candles + [future], 1)
    assert result.anchor_2 and result.anchor_2.source_candle_end <= NOW
    assert result.relation_to_trendline is RelationToTrendline.BELOW


def test_current_price_break_source_remains_provisional_only() -> None:
    result = evaluate(series(ASC_HIGHS, ASC_LOWS), 1, break_price_source=BreakPriceSource.CURRENT_PRICE)
    assert result.relation_to_trendline is RelationToTrendline.BELOW
    assert "current_price_cannot_confirm_break" in result.warnings


def test_invalid_candle_overlap_and_timezone_mix_fail_closed() -> None:
    candles = series(ASC_HIGHS, ASC_LOWS)
    invalid_close = [replace(candles[0], close=999), *candles[1:]]
    overlap = [candles[0], replace(candles[1], start=candles[0].start), *candles[2:]]
    naive = [replace(candles[0], start=candles[0].start.replace(tzinfo=None), end=candles[0].end.replace(tzinfo=None)), *candles[1:]]
    assert evaluate(invalid_close, 11).data_status is DataStatus.INVALID
    assert evaluate(overlap, 11).data_status is DataStatus.INVALID
    assert evaluate(naive, 11).data_status is DataStatus.INVALID


def test_anchor_age_expiry_and_candle_range_tolerance_mode() -> None:
    old = series(ASC_HIGHS, ASC_LOWS, start=NOW - timedelta(days=10))
    expired = evaluate(old, 11, maximum_anchor_age_by_timeframe={item: timedelta(hours=1) for item in PositionTimeframe}, stale_after_by_timeframe={item: timedelta(days=30) for item in PositionTimeframe})
    fraction = evaluate(series(ASC_HIGHS, ASC_LOWS), 11, tolerance_mode=ToleranceMode.CANDLE_RANGE_FRACTION, tolerance_value_by_timeframe={item: Decimal("0.1") for item in PositionTimeframe})
    assert expired.trend_state is TrendState.NO_VALID_TRENDLINE
    assert fraction.active_trendline_type is TrendlineType.ASCENDING


def test_all_timeframes_are_present_and_isolated() -> None:
    valid = series(ASC_HIGHS, ASC_LOWS)
    results = evaluate_all_trendlines(
        {PositionTimeframe.M15: valid, PositionTimeframe.M60: [valid[0]]},
        {PositionTimeframe.M15: 11, PositionTimeframe.M60: 10}, NOW, config(),
    )
    assert set(results) == set(PositionTimeframe)
    assert results[PositionTimeframe.M15].active_trendline_type is TrendlineType.ASCENDING
    assert results[PositionTimeframe.M60].data_status is DataStatus.INSUFFICIENT_DATA
    assert results[PositionTimeframe.D1].data_status is DataStatus.INVALID
    assert results[PositionTimeframe.W1].data_status is DataStatus.INVALID


def test_config_rejects_invalid_tolerance_and_slope_bounds() -> None:
    with pytest.raises(ValueError):
        config(tolerance_value_by_timeframe={item: Decimal("0") for item in PositionTimeframe})
    with pytest.raises(ValueError):
        config(minimum_absolute_slope=Decimal("1"), maximum_absolute_slope=Decimal("1"))
