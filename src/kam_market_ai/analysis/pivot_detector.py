"""Deterministic confirmed-pivot detection for KAM Trade V3 Trend Engine."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Sequence

from ..models import Candle
from .position_engine import PositionTimeframe


class PivotType(StrEnum):
    HIGH = "pivot_high"
    LOW = "pivot_low"


class PlateauPolicy(StrEnum):
    STRICT = "strict"
    FIRST = "first"
    LAST = "last"
    REJECT_PLATEAU = "reject_plateau"


@dataclass(frozen=True, slots=True)
class Pivot:
    pivot_type: PivotType
    timeframe: PositionTimeframe
    candle_index: int
    timestamp: datetime
    price: Decimal
    left_window: int
    right_window: int
    confirmed: bool
    source_candle_end: datetime
    warnings: tuple[str, ...] = ()


def _is_pivot(value: Decimal, left: Sequence[Decimal], right: Sequence[Decimal], pivot_type: PivotType, policy: PlateauPolicy) -> bool:
    values = (*left, *right)
    if pivot_type is PivotType.HIGH:
        strict = all(value > item for item in values)
        non_strict = all(value >= item for item in values)
    else:
        strict = all(value < item for item in values)
        non_strict = all(value <= item for item in values)
    if policy in (PlateauPolicy.STRICT, PlateauPolicy.REJECT_PLATEAU):
        return strict
    if not non_strict:
        return False
    if policy is PlateauPolicy.FIRST:
        return all(value != item for item in left)
    return all(value != item for item in right)


def detect_confirmed_pivots(
    timeframe: PositionTimeframe,
    candles: Sequence[Candle],
    *,
    left_window: int,
    right_window: int,
    plateau_policy: PlateauPolicy,
    index_offset: int = 0,
) -> tuple[Pivot, ...]:
    """Return only pivots confirmed by completed candles supplied by the caller."""

    if left_window <= 0 or right_window <= 0:
        raise ValueError("Pivot windows must be positive.")
    pivots: list[Pivot] = []
    for index in range(left_window, len(candles) - right_window):
        candle = candles[index]
        for pivot_type, field in ((PivotType.HIGH, "high"), (PivotType.LOW, "low")):
            value = Decimal(str(getattr(candle, field)))
            left = [Decimal(str(getattr(item, field))) for item in candles[index - left_window:index]]
            right = [Decimal(str(getattr(item, field))) for item in candles[index + 1:index + right_window + 1]]
            if _is_pivot(value, left, right, pivot_type, plateau_policy):
                pivots.append(Pivot(
                    pivot_type=pivot_type, timeframe=timeframe, candle_index=index + index_offset,
                    timestamp=candle.end, price=value, left_window=left_window,
                    right_window=right_window, confirmed=True,
                    source_candle_end=candle.end,
                    warnings=("plateau_policy_provisional",) if plateau_policy is PlateauPolicy.REJECT_PLATEAU else (),
                ))
    return tuple(pivots)
