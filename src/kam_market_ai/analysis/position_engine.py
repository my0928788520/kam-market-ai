"""Fail-closed, offline range-position engine for KAM Trade V3."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from typing import Mapping, Sequence

from ..models import Candle


class PositionTimeframe(StrEnum):
    M5 = "5m"
    M15 = "15m"
    M60 = "60m"
    D1 = "1d"
    W1 = "1w"


class RangeState(StrEnum):
    BREAKOUT_UP = "breakout_up"
    NEAR_HIGH = "near_high"
    UPPER_HALF = "upper_half"
    MIDDLE = "middle"
    LOWER_HALF = "lower_half"
    NEAR_LOW = "near_low"
    BREAKDOWN_DOWN = "breakdown_down"
    INSUFFICIENT_DATA = "insufficient_data"


class DataStatus(StrEnum):
    OK = "ok"
    INSUFFICIENT_DATA = "insufficient_data"
    STALE = "stale"
    INVALID = "invalid"
    CALCULATION_ERROR = "calculation_error"


class DuplicateTimestampPolicy(StrEnum):
    REJECT = "reject"
    KEEP_FIRST = "keep_first"
    KEEP_LAST = "keep_last"


ALL_TIMEFRAMES = (
    PositionTimeframe.M5,
    PositionTimeframe.M15,
    PositionTimeframe.M60,
    PositionTimeframe.D1,
    PositionTimeframe.W1,
)


@dataclass(frozen=True, slots=True)
class PositionEngineConfig:
    """All provisional V3 parameters are centralized here for later validation."""

    lookback_by_timeframe: Mapping[PositionTimeframe, int]
    minimum_closed_candles_by_timeframe: Mapping[PositionTimeframe, int]
    stale_after_by_timeframe: Mapping[PositionTimeframe, timedelta]
    near_low_threshold: Decimal
    lower_half_threshold: Decimal
    middle_threshold: Decimal
    upper_half_threshold: Decimal
    near_high_threshold: Decimal
    allow_sort_input: bool = True
    duplicate_timestamp_policy: DuplicateTimestampPolicy = DuplicateTimestampPolicy.REJECT

    def __post_init__(self) -> None:
        for name, values in (
            ("lookback_by_timeframe", self.lookback_by_timeframe),
            ("minimum_closed_candles_by_timeframe", self.minimum_closed_candles_by_timeframe),
            ("stale_after_by_timeframe", self.stale_after_by_timeframe),
        ):
            missing = set(ALL_TIMEFRAMES).difference(values)
            if missing:
                raise ValueError(f"{name} is missing timeframes: {sorted(item.value for item in missing)}")
        for timeframe in ALL_TIMEFRAMES:
            lookback = self.lookback_by_timeframe[timeframe]
            minimum = self.minimum_closed_candles_by_timeframe[timeframe]
            stale_after = self.stale_after_by_timeframe[timeframe]
            if not isinstance(lookback, int) or lookback <= 0:
                raise ValueError(f"lookback for {timeframe.value} must be a positive integer.")
            if not isinstance(minimum, int) or minimum <= 0 or minimum > lookback:
                raise ValueError(f"minimum closed candles for {timeframe.value} must be within lookback.")
            if not isinstance(stale_after, timedelta) or stale_after <= timedelta(0):
                raise ValueError(f"stale_after for {timeframe.value} must be positive.")
        thresholds = (
            self.near_low_threshold,
            self.lower_half_threshold,
            self.middle_threshold,
            self.upper_half_threshold,
            self.near_high_threshold,
        )
        if any(not isinstance(value, Decimal) or not value.is_finite() for value in thresholds):
            raise ValueError("Range thresholds must be finite Decimal values.")
        if not (Decimal("0") < thresholds[0] < thresholds[1] < thresholds[2] < thresholds[3] < thresholds[4]):
            raise ValueError("Range thresholds must be strictly increasing.")
        if self.near_high_threshold != Decimal("100"):
            raise ValueError("near_high_threshold must be exactly 100 for range classification.")

    @classmethod
    def provisional(cls) -> "PositionEngineConfig":
        """PROVISIONAL defaults; require manual validation before live use."""

        return cls(
            lookback_by_timeframe={
                PositionTimeframe.M5: 48,
                PositionTimeframe.M15: 32,
                PositionTimeframe.M60: 24,
                PositionTimeframe.D1: 20,
                PositionTimeframe.W1: 16,
            },
            minimum_closed_candles_by_timeframe={
                PositionTimeframe.M5: 24,
                PositionTimeframe.M15: 16,
                PositionTimeframe.M60: 12,
                PositionTimeframe.D1: 10,
                PositionTimeframe.W1: 8,
            },
            stale_after_by_timeframe={
                PositionTimeframe.M5: timedelta(minutes=10),
                PositionTimeframe.M15: timedelta(minutes=30),
                PositionTimeframe.M60: timedelta(hours=2),
                PositionTimeframe.D1: timedelta(days=2),
                PositionTimeframe.W1: timedelta(days=14),
            },
            near_low_threshold=Decimal("20"),
            lower_half_threshold=Decimal("40"),
            middle_threshold=Decimal("60"),
            upper_half_threshold=Decimal("80"),
            near_high_threshold=Decimal("100"),
        )


@dataclass(frozen=True, slots=True)
class PositionRangeResult:
    timeframe: PositionTimeframe
    range_high: Decimal | None
    range_low: Decimal | None
    range_width: Decimal | None
    current_price: Decimal | None
    position_percent: Decimal | None
    distance_to_high: Decimal | None
    distance_to_low: Decimal | None
    range_state: RangeState
    data_status: DataStatus
    candle_count: int
    lookback_used: int
    evaluated_at: datetime
    warnings: tuple[str, ...]


def _decimal(value: object) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        converted = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    return converted if converted.is_finite() else None


def _empty_result(
    timeframe: PositionTimeframe,
    evaluated_at: datetime,
    status: DataStatus,
    warnings: Sequence[str],
    *,
    candle_count: int = 0,
    current_price: Decimal | None = None,
) -> PositionRangeResult:
    return PositionRangeResult(
        timeframe=timeframe, range_high=None, range_low=None, range_width=None,
        current_price=current_price, position_percent=None, distance_to_high=None,
        distance_to_low=None, range_state=RangeState.INSUFFICIENT_DATA,
        data_status=status, candle_count=candle_count, lookback_used=0,
        evaluated_at=evaluated_at, warnings=tuple(warnings),
    )


def _validate_candle(candle: Candle) -> str | None:
    values = (candle.open, candle.high, candle.low, candle.close)
    decimals = tuple(_decimal(value) for value in values)
    if any(value is None or value <= 0 for value in decimals):
        return "invalid_candle_price"
    if decimals[1] < decimals[2]:
        return "invalid_candle_high_below_low"
    if candle.start >= candle.end:
        return "invalid_candle_time_range"
    return None


def _prepare_candles(
    candles: Sequence[Candle], config: PositionEngineConfig
) -> tuple[list[Candle] | None, tuple[str, ...]]:
    warnings: list[str] = []
    for candle in candles:
        if not isinstance(candle, Candle):
            return None, ("invalid_candle_type",)
        issue = _validate_candle(candle)
        if issue:
            return None, (issue,)
    prepared = list(candles)
    if any(prepared[index].end > prepared[index + 1].end for index in range(len(prepared) - 1)):
        if not config.allow_sort_input:
            return None, ("candles_out_of_order",)
        prepared.sort(key=lambda candle: candle.end)
        warnings.append("candles_sorted_by_end")
    duplicates = {candle.end for candle in prepared if sum(item.end == candle.end for item in prepared) > 1}
    if duplicates:
        if config.duplicate_timestamp_policy is DuplicateTimestampPolicy.REJECT:
            return None, ("duplicate_candle_timestamp",)
        deduplicated: dict[datetime, Candle] = {}
        for candle in prepared:
            if config.duplicate_timestamp_policy is DuplicateTimestampPolicy.KEEP_FIRST:
                deduplicated.setdefault(candle.end, candle)
            else:
                deduplicated[candle.end] = candle
        prepared = list(deduplicated.values())
        warnings.append(f"duplicate_timestamps_{config.duplicate_timestamp_policy.value}")
    return prepared, tuple(warnings)


def _range_state(position_percent: Decimal, config: PositionEngineConfig) -> RangeState:
    if position_percent > config.near_high_threshold:
        return RangeState.BREAKOUT_UP
    if position_percent < Decimal("0"):
        return RangeState.BREAKDOWN_DOWN
    if position_percent <= config.near_low_threshold:
        return RangeState.NEAR_LOW
    if position_percent <= config.lower_half_threshold:
        return RangeState.LOWER_HALF
    if position_percent <= config.middle_threshold:
        return RangeState.MIDDLE
    if position_percent <= config.upper_half_threshold:
        return RangeState.UPPER_HALF
    return RangeState.NEAR_HIGH


def evaluate_position_range(
    timeframe: PositionTimeframe,
    candles: Sequence[Candle],
    current_price: object,
    evaluated_at: datetime,
    config: PositionEngineConfig,
) -> PositionRangeResult:
    """Evaluate one timeframe without creating directional or trading decisions."""

    price = _decimal(current_price)
    if price is None or price <= 0:
        return _empty_result(timeframe, evaluated_at, DataStatus.INVALID, ("invalid_current_price",), candle_count=len(candles))
    prepared, warnings = _prepare_candles(candles, config)
    if prepared is None:
        return _empty_result(timeframe, evaluated_at, DataStatus.INVALID, warnings, candle_count=len(candles), current_price=price)
    try:
        closed = [candle for candle in prepared if candle.end <= evaluated_at]
    except TypeError:
        return _empty_result(timeframe, evaluated_at, DataStatus.INVALID, ("incompatible_candle_timestamp",), candle_count=len(prepared), current_price=price)
    minimum = config.minimum_closed_candles_by_timeframe[timeframe]
    if len(closed) < minimum:
        return _empty_result(
            timeframe, evaluated_at, DataStatus.INSUFFICIENT_DATA,
            (*warnings, "insufficient_closed_candles"), candle_count=len(prepared), current_price=price,
        )
    lookback = config.lookback_by_timeframe[timeframe]
    sample = closed[-lookback:]
    try:
        range_high = max(_decimal(candle.high) for candle in sample)
        range_low = min(_decimal(candle.low) for candle in sample)
        if range_high is None or range_low is None:
            raise ArithmeticError("invalid range values")
        width = range_high - range_low
        if width <= 0:
            return _empty_result(
                timeframe, evaluated_at, DataStatus.INVALID, (*warnings, "invalid_range_width"),
                candle_count=len(prepared), current_price=price,
            )
        position_percent = (price - range_low) / width * Decimal("100")
        latest_end = prepared[-1].end
        stale = evaluated_at - latest_end > config.stale_after_by_timeframe[timeframe]
        return PositionRangeResult(
            timeframe=timeframe, range_high=range_high, range_low=range_low, range_width=width,
            current_price=price, position_percent=position_percent,
            distance_to_high=range_high - price, distance_to_low=price - range_low,
            range_state=_range_state(position_percent, config),
            data_status=DataStatus.STALE if stale else DataStatus.OK,
            candle_count=len(prepared), lookback_used=len(sample), evaluated_at=evaluated_at,
            warnings=(*warnings, "stale_market_data") if stale else warnings,
        )
    except (ArithmeticError, InvalidOperation, TypeError, ValueError) as error:
        return _empty_result(
            timeframe, evaluated_at, DataStatus.CALCULATION_ERROR,
            (*warnings, f"calculation_error:{type(error).__name__}"), candle_count=len(prepared), current_price=price,
        )


def evaluate_all_position_ranges(
    candles_by_timeframe: Mapping[PositionTimeframe, Sequence[Candle]],
    current_price: object | Mapping[PositionTimeframe, object],
    evaluated_at: datetime,
    config: PositionEngineConfig,
) -> dict[PositionTimeframe, PositionRangeResult]:
    """Thin isolation boundary: failure in one timeframe cannot affect another."""

    results: dict[PositionTimeframe, PositionRangeResult] = {}
    for timeframe in ALL_TIMEFRAMES:
        price = current_price.get(timeframe) if isinstance(current_price, Mapping) else current_price
        candles = candles_by_timeframe.get(timeframe, ())
        try:
            results[timeframe] = evaluate_position_range(timeframe, candles, price, evaluated_at, config)
        except Exception as error:  # defensive boundary; the error is preserved in diagnostics
            results[timeframe] = _empty_result(
                timeframe, evaluated_at, DataStatus.CALCULATION_ERROR,
                (f"unexpected_calculation_error:{type(error).__name__}",), candle_count=len(candles),
            )
    return results
