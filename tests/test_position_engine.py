from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from kam_market_ai.analysis.position_engine import (
    DataStatus,
    DuplicateTimestampPolicy,
    PositionEngineConfig,
    PositionTimeframe,
    RangeState,
    evaluate_all_position_ranges,
    evaluate_position_range,
)
from kam_market_ai.models import Candle, Instrument


NOW = datetime(2026, 7, 31, 10, tzinfo=UTC)


def candle(index: int, low: float = 90, high: float = 110, *, closed: bool = True, close: float = 100) -> Candle:
    end = NOW - timedelta(minutes=30 - index) if closed else NOW + timedelta(minutes=1)
    return Candle(Instrument.MTX, end - timedelta(minutes=1), end, 100, high, low, close, 1)


def config(**changes: object) -> PositionEngineConfig:
    value = PositionEngineConfig.provisional()
    return PositionEngineConfig(
        lookback_by_timeframe=changes.get("lookback_by_timeframe", {item: 4 for item in PositionTimeframe}),
        minimum_closed_candles_by_timeframe=changes.get("minimum_closed_candles_by_timeframe", {item: 2 for item in PositionTimeframe}),
        stale_after_by_timeframe=changes.get("stale_after_by_timeframe", {item: timedelta(hours=1) for item in PositionTimeframe}),
        near_low_threshold=changes.get("near_low_threshold", value.near_low_threshold),
        lower_half_threshold=changes.get("lower_half_threshold", value.lower_half_threshold),
        middle_threshold=changes.get("middle_threshold", value.middle_threshold),
        upper_half_threshold=changes.get("upper_half_threshold", value.upper_half_threshold),
        near_high_threshold=changes.get("near_high_threshold", value.near_high_threshold),
        allow_sort_input=changes.get("allow_sort_input", True),
        duplicate_timestamp_policy=changes.get("duplicate_timestamp_policy", DuplicateTimestampPolicy.REJECT),
    )


def evaluate(price: object, candles: list[Candle] | None = None, **config_changes: object):
    return evaluate_position_range(PositionTimeframe.M15, candles or [candle(index) for index in range(4)], price, NOW, config(**config_changes))


@pytest.mark.parametrize(("price", "state"), [
    (50, RangeState.BREAKDOWN_DOWN), (90, RangeState.NEAR_LOW), (95, RangeState.LOWER_HALF),
    (100, RangeState.MIDDLE), (105, RangeState.UPPER_HALF), (109, RangeState.NEAR_HIGH),
    (110, RangeState.NEAR_HIGH), (111, RangeState.BREAKOUT_UP),
])
def test_range_position_states(price: float, state: RangeState) -> None:
    result = evaluate(price)
    assert result.range_state is state and result.data_status is DataStatus.OK


def test_formula_and_unbounded_percentages() -> None:
    upper = evaluate(120)
    lower = evaluate(80)
    assert upper.range_width == Decimal("20") and upper.position_percent == Decimal("150")
    assert upper.distance_to_high == Decimal("-10") and lower.position_percent == Decimal("-50")
    assert lower.distance_to_low == Decimal("-10")


def test_zero_or_inverted_range_is_invalid() -> None:
    flat = [candle(index, low=100, high=100) for index in range(4)]
    inverted = [candle(index, low=111, high=110) for index in range(4)]
    assert evaluate(100, flat).data_status is DataStatus.INVALID
    assert evaluate(100, inverted).data_status is DataStatus.INVALID


@pytest.mark.parametrize("price", [None, "NaN", float("nan"), 0, -1])
def test_invalid_current_price_fails_closed(price: object) -> None:
    assert evaluate(price).data_status is DataStatus.INVALID


def test_invalid_candle_nan_and_bad_bounds_fail_closed() -> None:
    bad_nan = [candle(0, high=float("nan")), candle(1), candle(2), candle(3)]
    bad_bounds = [candle(0, low=120, high=110), candle(1), candle(2), candle(3)]
    assert evaluate(100, bad_nan).data_status is DataStatus.INVALID
    assert evaluate(100, bad_bounds).data_status is DataStatus.INVALID


def test_incomplete_candle_does_not_set_range_boundaries() -> None:
    candles = [candle(index) for index in range(3)] + [candle(3, low=1, high=999, closed=False)]
    result = evaluate(105, candles)
    assert result.range_low == Decimal("90") and result.range_high == Decimal("110")
    assert result.candle_count == 4 and result.lookback_used == 3


def test_insufficient_closed_candles() -> None:
    result = evaluate(100, [candle(0), candle(1, closed=False)])
    assert result.data_status is DataStatus.INSUFFICIENT_DATA
    assert result.range_state is RangeState.INSUFFICIENT_DATA


def test_out_of_order_sorting_warns_or_rejects() -> None:
    candles = [candle(2), candle(0), candle(1), candle(3)]
    sorted_result = evaluate(100, candles)
    rejected_result = evaluate(100, candles, allow_sort_input=False)
    assert "candles_sorted_by_end" in sorted_result.warnings
    assert rejected_result.data_status is DataStatus.INVALID


def test_duplicate_timestamp_policy_is_explicit() -> None:
    duplicate = [candle(0), candle(0, low=80, high=120), candle(1), candle(2)]
    rejected = evaluate(100, duplicate)
    kept = evaluate(100, duplicate, duplicate_timestamp_policy=DuplicateTimestampPolicy.KEEP_LAST)
    assert rejected.data_status is DataStatus.INVALID
    assert kept.data_status is DataStatus.OK and "duplicate_timestamps_keep_last" in kept.warnings


def test_stale_data_status() -> None:
    old = [Candle(Instrument.MTX, NOW - timedelta(hours=4, minutes=index + 1), NOW - timedelta(hours=4, minutes=index), 100, 110, 90, 100, 1) for index in range(4)]
    result = evaluate(100, old)
    assert result.data_status is DataStatus.STALE and "stale_market_data" in result.warnings


def test_invalid_threshold_order_rejects_startup() -> None:
    with pytest.raises(ValueError, match="strictly increasing"):
        config(lower_half_threshold=Decimal("20"))


def test_all_timeframes_are_present_and_isolated() -> None:
    candles = [candle(index) for index in range(4)]
    results = evaluate_all_position_ranges(
        {PositionTimeframe.M15: candles, PositionTimeframe.M60: [candle(0)]},
        {PositionTimeframe.M15: 111, PositionTimeframe.M60: 100}, NOW, config(),
    )
    assert set(results) == set(PositionTimeframe)
    assert results[PositionTimeframe.M15].range_state is RangeState.BREAKOUT_UP
    assert results[PositionTimeframe.M60].data_status is DataStatus.INSUFFICIENT_DATA
    assert results[PositionTimeframe.D1].data_status is DataStatus.INVALID
    assert results[PositionTimeframe.W1].data_status is DataStatus.INVALID
