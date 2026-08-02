from __future__ import annotations

from datetime import UTC, datetime, timedelta

from kam_market_ai.analysis.pivot_detector import PlateauPolicy, PivotType, detect_confirmed_pivots
from kam_market_ai.analysis.position_engine import PositionTimeframe
from kam_market_ai.models import Candle, Instrument


NOW = datetime(2026, 7, 31, 10, tzinfo=UTC)


def candle(index: int, high: int, low: int) -> Candle:
    end = NOW - timedelta(minutes=10 - index)
    return Candle(Instrument.MTX, end - timedelta(minutes=1), end, low + 1, high, low, low + 1, 1)


def test_detects_confirmed_high_and_low_without_future_candles() -> None:
    candles = [candle(index, high, low) for index, (high, low) in enumerate(((12, 8), (13, 7), (15, 6), (13, 7), (12, 8)))]
    pivots = detect_confirmed_pivots(PositionTimeframe.M15, candles, left_window=2, right_window=2, plateau_policy=PlateauPolicy.REJECT_PLATEAU)
    assert {(pivot.pivot_type, pivot.candle_index) for pivot in pivots} == {(PivotType.HIGH, 2), (PivotType.LOW, 2)}


def test_window_edges_and_plateau_policy_are_deterministic() -> None:
    candles = [candle(index, high, low) for index, (high, low) in enumerate(((10, 8), (12, 7), (12, 6), (10, 7), (9, 8)))]
    rejected = detect_confirmed_pivots(PositionTimeframe.M15, candles, left_window=1, right_window=1, plateau_policy=PlateauPolicy.REJECT_PLATEAU)
    first = detect_confirmed_pivots(PositionTimeframe.M15, candles, left_window=1, right_window=1, plateau_policy=PlateauPolicy.FIRST)
    last = detect_confirmed_pivots(PositionTimeframe.M15, candles, left_window=1, right_window=1, plateau_policy=PlateauPolicy.LAST)
    assert not [pivot for pivot in rejected if pivot.pivot_type is PivotType.HIGH]
    assert [pivot.candle_index for pivot in first if pivot.pivot_type is PivotType.HIGH] == [1]
    assert [pivot.candle_index for pivot in last if pivot.pivot_type is PivotType.HIGH] == [2]


def test_right_window_shortage_cannot_confirm_a_pivot() -> None:
    candles = [candle(index, high, low) for index, (high, low) in enumerate(((10, 8), (11, 7), (20, 6)))]
    pivots = detect_confirmed_pivots(PositionTimeframe.M15, candles, left_window=1, right_window=1, plateau_policy=PlateauPolicy.STRICT)
    assert all(pivot.candle_index != 2 for pivot in pivots)
