"""Offline, fail-closed trendline engine for KAM Trade V3."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from typing import Mapping, Sequence

from ..models import Candle
from .pivot_detector import PlateauPolicy, Pivot, PivotType, detect_confirmed_pivots
from .position_engine import ALL_TIMEFRAMES, DataStatus, PositionTimeframe


class TrendlineType(StrEnum):
    ASCENDING = "ascending"
    DESCENDING = "descending"
    NONE = "none"
    AMBIGUOUS = "ambiguous"


class RelationToTrendline(StrEnum):
    ABOVE = "above"
    BELOW = "below"
    TOUCHING = "touching"
    BREAKOUT_UP = "breakout_up"
    BREAKDOWN_DOWN = "breakdown_down"
    RETEST = "retest"
    REJECTION = "rejection"
    INSUFFICIENT_DATA = "insufficient_data"
    AMBIGUOUS = "ambiguous"
    INVALID = "invalid"


class TrendState(StrEnum):
    ASCENDING_SUPPORTED = "ascending_supported"
    ASCENDING_BROKEN = "ascending_broken"
    ASCENDING_RETEST = "ascending_retest"
    DESCENDING_RESISTED = "descending_resisted"
    DESCENDING_BROKEN = "descending_broken"
    DESCENDING_RETEST = "descending_retest"
    NO_VALID_TRENDLINE = "no_valid_trendline"
    AMBIGUOUS = "ambiguous"
    INSUFFICIENT_DATA = "insufficient_data"
    STALE = "stale"
    INVALID = "invalid"
    CALCULATION_ERROR = "calculation_error"


class ToleranceMode(StrEnum):
    FIXED_POINTS = "fixed_points"
    PERCENTAGE = "percentage"
    CANDLE_RANGE_FRACTION = "candle_range_fraction"


class BreakPriceSource(StrEnum):
    CLOSE = "close"
    HIGH_LOW = "high_low"
    CURRENT_PRICE = "current_price"


class TrendDuplicateTimestampPolicy(StrEnum):
    REJECT = "reject"
    KEEP_FIRST = "keep_first"
    KEEP_LAST = "keep_last"


@dataclass(frozen=True, slots=True)
class TrendEngineConfig:
    """Single typed location for all PROVISIONAL Trend Engine parameters."""

    lookback_by_timeframe: Mapping[PositionTimeframe, int]
    minimum_closed_candles_by_timeframe: Mapping[PositionTimeframe, int]
    pivot_left_window_by_timeframe: Mapping[PositionTimeframe, int]
    pivot_right_window_by_timeframe: Mapping[PositionTimeframe, int]
    minimum_anchor_separation_by_timeframe: Mapping[PositionTimeframe, int]
    maximum_anchor_age_by_timeframe: Mapping[PositionTimeframe, timedelta]
    tolerance_value_by_timeframe: Mapping[PositionTimeframe, Decimal]
    break_confirmation_bars_by_timeframe: Mapping[PositionTimeframe, int]
    retest_max_bars_by_timeframe: Mapping[PositionTimeframe, int]
    stale_after_by_timeframe: Mapping[PositionTimeframe, timedelta]
    plateau_policy: PlateauPolicy = PlateauPolicy.REJECT_PLATEAU
    tolerance_mode: ToleranceMode = ToleranceMode.PERCENTAGE
    break_price_source: BreakPriceSource = BreakPriceSource.CLOSE
    maximum_violation_count: int = 0
    minimum_touch_count: int = 0
    allow_sort_input: bool = True
    duplicate_timestamp_policy: TrendDuplicateTimestampPolicy = TrendDuplicateTimestampPolicy.REJECT
    ambiguity_score_gap: Decimal = Decimal("0.10")
    minimum_absolute_slope: Decimal = Decimal("0.0000001")
    maximum_absolute_slope: Decimal = Decimal("1000")
    recency_weight: Decimal = Decimal("1")
    touch_weight: Decimal = Decimal("1")
    violation_weight: Decimal = Decimal("2")
    anchor_separation_weight: Decimal = Decimal("1")
    slope_validity_weight: Decimal = Decimal("1")

    def __post_init__(self) -> None:
        mappings = (
            ("lookback_by_timeframe", self.lookback_by_timeframe),
            ("minimum_closed_candles_by_timeframe", self.minimum_closed_candles_by_timeframe),
            ("pivot_left_window_by_timeframe", self.pivot_left_window_by_timeframe),
            ("pivot_right_window_by_timeframe", self.pivot_right_window_by_timeframe),
            ("minimum_anchor_separation_by_timeframe", self.minimum_anchor_separation_by_timeframe),
            ("maximum_anchor_age_by_timeframe", self.maximum_anchor_age_by_timeframe),
            ("tolerance_value_by_timeframe", self.tolerance_value_by_timeframe),
            ("break_confirmation_bars_by_timeframe", self.break_confirmation_bars_by_timeframe),
            ("retest_max_bars_by_timeframe", self.retest_max_bars_by_timeframe),
            ("stale_after_by_timeframe", self.stale_after_by_timeframe),
        )
        for name, values in mappings:
            missing = set(ALL_TIMEFRAMES).difference(values)
            if missing:
                raise ValueError(f"{name} is missing timeframes: {sorted(item.value for item in missing)}")
        for timeframe in ALL_TIMEFRAMES:
            lookback = self.lookback_by_timeframe[timeframe]
            minimum = self.minimum_closed_candles_by_timeframe[timeframe]
            integer_values = (
                ("lookback", lookback), ("minimum closed candles", minimum),
                ("pivot left window", self.pivot_left_window_by_timeframe[timeframe]),
                ("pivot right window", self.pivot_right_window_by_timeframe[timeframe]),
                ("minimum anchor separation", self.minimum_anchor_separation_by_timeframe[timeframe]),
                ("break confirmation bars", self.break_confirmation_bars_by_timeframe[timeframe]),
                ("retest max bars", self.retest_max_bars_by_timeframe[timeframe]),
            )
            if any(not isinstance(value, int) or value <= 0 for _, value in integer_values):
                raise ValueError(f"All integer settings for {timeframe.value} must be positive.")
            if minimum > lookback:
                raise ValueError(f"minimum closed candles for {timeframe.value} must be within lookback.")
            if any(not isinstance(value, timedelta) or value <= timedelta(0) for value in (self.maximum_anchor_age_by_timeframe[timeframe], self.stale_after_by_timeframe[timeframe])):
                raise ValueError(f"Age settings for {timeframe.value} must be positive timedeltas.")
            tolerance = self.tolerance_value_by_timeframe[timeframe]
            if not isinstance(tolerance, Decimal) or not tolerance.is_finite() or tolerance <= 0:
                raise ValueError(f"tolerance for {timeframe.value} must be a positive finite Decimal.")
        decimals = (self.ambiguity_score_gap, self.minimum_absolute_slope, self.maximum_absolute_slope,
                    self.recency_weight, self.touch_weight, self.violation_weight,
                    self.anchor_separation_weight, self.slope_validity_weight)
        if any(not isinstance(value, Decimal) or not value.is_finite() or value < 0 for value in decimals):
            raise ValueError("Trend score and slope settings must be finite non-negative Decimals.")
        if not self.minimum_absolute_slope < self.maximum_absolute_slope:
            raise ValueError("minimum_absolute_slope must be lower than maximum_absolute_slope.")
        if self.maximum_violation_count < 0 or self.minimum_touch_count < 0:
            raise ValueError("Violation and touch counts cannot be negative.")

    @classmethod
    def provisional(cls) -> "TrendEngineConfig":
        """PROVISIONAL engineering defaults; not validated trading rules."""

        return cls(
            lookback_by_timeframe={PositionTimeframe.M15: 64, PositionTimeframe.M60: 48, PositionTimeframe.D1: 60, PositionTimeframe.W1: 52},
            minimum_closed_candles_by_timeframe={PositionTimeframe.M15: 32, PositionTimeframe.M60: 24, PositionTimeframe.D1: 30, PositionTimeframe.W1: 26},
            pivot_left_window_by_timeframe={item: 2 for item in ALL_TIMEFRAMES},
            pivot_right_window_by_timeframe={item: 2 for item in ALL_TIMEFRAMES},
            minimum_anchor_separation_by_timeframe={PositionTimeframe.M15: 4, PositionTimeframe.M60: 3, PositionTimeframe.D1: 3, PositionTimeframe.W1: 2},
            maximum_anchor_age_by_timeframe={PositionTimeframe.M15: timedelta(days=2), PositionTimeframe.M60: timedelta(days=5), PositionTimeframe.D1: timedelta(days=180), PositionTimeframe.W1: timedelta(days=730)},
            tolerance_value_by_timeframe={item: Decimal("0.10") for item in ALL_TIMEFRAMES},
            break_confirmation_bars_by_timeframe={PositionTimeframe.M15: 2, PositionTimeframe.M60: 2, PositionTimeframe.D1: 2, PositionTimeframe.W1: 1},
            retest_max_bars_by_timeframe={PositionTimeframe.M15: 8, PositionTimeframe.M60: 6, PositionTimeframe.D1: 5, PositionTimeframe.W1: 4},
            stale_after_by_timeframe={PositionTimeframe.M15: timedelta(minutes=30), PositionTimeframe.M60: timedelta(hours=2), PositionTimeframe.D1: timedelta(days=2), PositionTimeframe.W1: timedelta(days=14)},
        )


@dataclass(frozen=True, slots=True)
class TrendlineResult:
    timeframe: PositionTimeframe
    active_trendline_type: TrendlineType
    anchor_1: Pivot | None
    anchor_2: Pivot | None
    slope_per_second: Decimal | None
    projected_value_at_evaluated_at: Decimal | None
    current_price: Decimal | None
    distance_to_trendline: Decimal | None
    distance_percent: Decimal | None
    relation_to_trendline: RelationToTrendline
    touch_count: int
    violation_count: int
    last_touch_at: datetime | None
    created_at: datetime | None
    valid: bool
    confidence: Decimal | None
    trend_state: TrendState
    data_status: DataStatus
    candle_count: int
    lookback_used: int
    evaluated_at: datetime
    warnings: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _Candidate:
    trendline_type: TrendlineType
    anchor_1: Pivot
    anchor_2: Pivot
    slope: Decimal
    touch_count: int
    violation_count: int
    last_touch_at: datetime | None
    break_index: int | None
    valid: bool
    warnings: tuple[str, ...]
    score: Decimal


def _decimal(value: object) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None
    return result if result.is_finite() else None


def _empty_result(timeframe: PositionTimeframe, evaluated_at: datetime, status: DataStatus, warnings: Sequence[str], *, candle_count: int = 0, current_price: Decimal | None = None) -> TrendlineResult:
    state = (TrendState.INVALID if status is DataStatus.INVALID else TrendState.STALE if status is DataStatus.STALE
             else TrendState.CALCULATION_ERROR if status is DataStatus.CALCULATION_ERROR else TrendState.INSUFFICIENT_DATA)
    relation = RelationToTrendline.INVALID if status is DataStatus.INVALID else RelationToTrendline.INSUFFICIENT_DATA
    return TrendlineResult(timeframe, TrendlineType.NONE, None, None, None, None, current_price, None, None,
                           relation, 0, 0, None, None, False, None, state, status, candle_count, 0,
                           evaluated_at, tuple(warnings))


def _no_trendline_result(timeframe: PositionTimeframe, evaluated_at: datetime, status: DataStatus, warnings: Sequence[str], *, candle_count: int, lookback_used: int, current_price: Decimal) -> TrendlineResult:
    state = TrendState.STALE if status is DataStatus.STALE else TrendState.NO_VALID_TRENDLINE
    return TrendlineResult(timeframe, TrendlineType.NONE, None, None, None, None, current_price, None, None,
                           RelationToTrendline.INSUFFICIENT_DATA, 0, 0, None, None, False, None, state,
                           status, candle_count, lookback_used, evaluated_at, tuple(warnings))


def _aware(value: datetime) -> bool:
    return value.tzinfo is not None and value.utcoffset() is not None


def _validate_and_prepare(candles: Sequence[Candle], evaluated_at: datetime, config: TrendEngineConfig) -> tuple[list[Candle] | None, tuple[str, ...]]:
    warnings: list[str] = []
    eval_aware = _aware(evaluated_at)
    for candle in candles:
        if not isinstance(candle, Candle):
            return None, ("invalid_candle_type",)
        if _aware(candle.start) != eval_aware or _aware(candle.end) != eval_aware:
            return None, ("mixed_or_incompatible_timezone",)
        if candle.start >= candle.end:
            return None, ("invalid_candle_time_range",)
        values = tuple(_decimal(value) for value in (candle.open, candle.high, candle.low, candle.close))
        if any(value is None or value <= 0 for value in values):
            return None, ("invalid_candle_price",)
        open_price, high, low, close = values
        if high < low:
            return None, ("invalid_candle_high_below_low",)
        if not low <= close <= high or not low <= open_price <= high:
            return None, ("invalid_candle_open_or_close_outside_range",)
    prepared = list(candles)
    if any(prepared[index].end > prepared[index + 1].end for index in range(len(prepared) - 1)):
        if not config.allow_sort_input:
            return None, ("candles_out_of_order",)
        prepared.sort(key=lambda candle: candle.end)
        warnings.append("candles_sorted_by_end")
    duplicate_ends = {item.end for item in prepared if sum(other.end == item.end for other in prepared) > 1}
    if duplicate_ends:
        if config.duplicate_timestamp_policy is TrendDuplicateTimestampPolicy.REJECT:
            return None, ("duplicate_candle_timestamp",)
        retained: dict[datetime, Candle] = {}
        for candle in prepared:
            if config.duplicate_timestamp_policy is TrendDuplicateTimestampPolicy.KEEP_FIRST:
                retained.setdefault(candle.end, candle)
            else:
                retained[candle.end] = candle
        prepared = list(retained.values())
        warnings.append(f"duplicate_timestamps_{config.duplicate_timestamp_policy.value}")
    if any(prepared[index].start < prepared[index - 1].end for index in range(1, len(prepared))):
        return None, (*warnings, "overlapping_candles")
    return prepared, tuple(warnings)


def _line_value(anchor: Pivot, slope: Decimal, timestamp: datetime) -> Decimal:
    seconds = Decimal(str((timestamp - anchor.timestamp).total_seconds()))
    return anchor.price + slope * seconds


def _tolerance(config: TrendEngineConfig, timeframe: PositionTimeframe, line_value: Decimal, candle: Candle | None) -> Decimal:
    value = config.tolerance_value_by_timeframe[timeframe]
    if config.tolerance_mode is ToleranceMode.FIXED_POINTS:
        return value
    if config.tolerance_mode is ToleranceMode.PERCENTAGE:
        return abs(line_value) * value / Decimal("100")
    if candle is None:
        return Decimal("0")
    high, low = _decimal(candle.high), _decimal(candle.low)
    assert high is not None and low is not None
    return (high - low) * value


def _break_price(candle: Candle, trendline_type: TrendlineType, source: BreakPriceSource) -> Decimal | None:
    if source is BreakPriceSource.CURRENT_PRICE:
        return None
    if source is BreakPriceSource.CLOSE:
        return _decimal(candle.close)
    return _decimal(candle.low if trendline_type is TrendlineType.ASCENDING else candle.high)


def _is_break(value: Decimal, line: Decimal, tolerance: Decimal, trendline_type: TrendlineType) -> bool:
    return value < line - tolerance if trendline_type is TrendlineType.ASCENDING else value > line + tolerance


def _candidate_from_anchors(timeframe: PositionTimeframe, trendline_type: TrendlineType, anchor_1: Pivot, anchor_2: Pivot, completed: Sequence[Candle], evaluated_at: datetime, config: TrendEngineConfig) -> _Candidate:
    warnings: list[str] = []
    separation = anchor_2.candle_index - anchor_1.candle_index
    seconds = Decimal(str((anchor_2.timestamp - anchor_1.timestamp).total_seconds()))
    slope = (anchor_2.price - anchor_1.price) / seconds if seconds > 0 else Decimal("0")
    expected_sign = slope > 0 if trendline_type is TrendlineType.ASCENDING else slope < 0
    if separation < config.minimum_anchor_separation_by_timeframe[timeframe]:
        warnings.append("anchor_separation_too_small")
    if not expected_sign:
        warnings.append("invalid_slope_direction")
    if not config.minimum_absolute_slope <= abs(slope) <= config.maximum_absolute_slope:
        warnings.append("slope_outside_provisional_bounds")
    age = evaluated_at - anchor_2.timestamp
    if age > config.maximum_anchor_age_by_timeframe[timeframe]:
        warnings.append("anchor_age_expired")
    touches = 0
    violations = 0
    last_touch: datetime | None = None
    break_index: int | None = None
    consecutive_breaks = 0
    anchor_start = anchor_2.candle_index + 1
    for index in range(anchor_start, len(completed)):
        candle = completed[index]
        line = _line_value(anchor_1, slope, candle.end)
        tolerance = _tolerance(config, timeframe, line, candle)
        extremum = _decimal(candle.low if trendline_type is TrendlineType.ASCENDING else candle.high)
        assert extremum is not None
        if abs(extremum - line) <= tolerance:
            touches += 1
            last_touch = candle.end
        price = _break_price(candle, trendline_type, config.break_price_source)
        if price is None:
            continue
        if _is_break(price, line, tolerance, trendline_type):
            violations += 1
            consecutive_breaks += 1
            if consecutive_breaks >= config.break_confirmation_bars_by_timeframe[timeframe]:
                break_index = index
        else:
            consecutive_breaks = 0
    if config.break_price_source is BreakPriceSource.CURRENT_PRICE:
        warnings.append("current_price_cannot_confirm_break")
    if touches < config.minimum_touch_count:
        warnings.append("insufficient_post_anchor_touches")
    if violations > config.maximum_violation_count:
        warnings.append("violation_count_exceeded")
    if break_index is not None:
        warnings.append("confirmed_break")
    valid = not warnings or all(item == "current_price_cannot_confirm_break" for item in warnings)
    recency = Decimal("1") / (Decimal("1") + Decimal(str(max(age.total_seconds(), 0))))
    separation_score = min(Decimal("1"), Decimal(separation) / Decimal(config.lookback_by_timeframe[timeframe]))
    score = (recency * config.recency_weight + Decimal(touches) * config.touch_weight
             - Decimal(violations) * config.violation_weight + separation_score * config.anchor_separation_weight
             + config.slope_validity_weight)
    return _Candidate(trendline_type, anchor_1, anchor_2, slope, touches, violations, last_touch,
                      break_index, valid, tuple(warnings), score)


def _build_candidates(timeframe: PositionTimeframe, pivots: Sequence[Pivot], completed: Sequence[Candle], evaluated_at: datetime, config: TrendEngineConfig) -> tuple[_Candidate, ...]:
    candidates: list[_Candidate] = []
    for pivot_type, trendline_type in ((PivotType.LOW, TrendlineType.ASCENDING), (PivotType.HIGH, TrendlineType.DESCENDING)):
        typed = [pivot for pivot in pivots if pivot.pivot_type is pivot_type]
        for first_index, first in enumerate(typed):
            for second in typed[first_index + 1:]:
                correct_direction = second.price > first.price if trendline_type is TrendlineType.ASCENDING else second.price < first.price
                if correct_direction:
                    candidates.append(_candidate_from_anchors(timeframe, trendline_type, first, second, completed, evaluated_at, config))
    return tuple(candidates)


def _relation(candidate: _Candidate, completed: Sequence[Candle], current_price: Decimal, evaluated_at: datetime, config: TrendEngineConfig) -> tuple[RelationToTrendline, TrendState]:
    line = _line_value(candidate.anchor_1, candidate.slope, evaluated_at)
    tolerance = _tolerance(config, candidate.anchor_1.timeframe, line, completed[-1] if completed else None)
    if candidate.break_index is not None:
        bars_since_break = len(completed) - 1 - candidate.break_index
        if abs(current_price - line) <= tolerance and bars_since_break <= config.retest_max_bars_by_timeframe[candidate.anchor_1.timeframe]:
            state = TrendState.ASCENDING_RETEST if candidate.trendline_type is TrendlineType.ASCENDING else TrendState.DESCENDING_RETEST
            return RelationToTrendline.RETEST, state
        post_break_touched = any(
            abs((_decimal(candle.low if candidate.trendline_type is TrendlineType.ASCENDING else candle.high) or Decimal("0")) - _line_value(candidate.anchor_1, candidate.slope, candle.end))
            <= _tolerance(config, candidate.anchor_1.timeframe, _line_value(candidate.anchor_1, candidate.slope, candle.end), candle)
            for candle in completed[candidate.break_index + 1:]
        )
        still_break_side = _is_break(current_price, line, tolerance, candidate.trendline_type)
        if post_break_touched and still_break_side:
            return RelationToTrendline.REJECTION, TrendState.ASCENDING_BROKEN if candidate.trendline_type is TrendlineType.ASCENDING else TrendState.DESCENDING_BROKEN
        return (RelationToTrendline.BREAKDOWN_DOWN if candidate.trendline_type is TrendlineType.ASCENDING else RelationToTrendline.BREAKOUT_UP,
                TrendState.ASCENDING_BROKEN if candidate.trendline_type is TrendlineType.ASCENDING else TrendState.DESCENDING_BROKEN)
    if abs(current_price - line) <= tolerance:
        relation = RelationToTrendline.TOUCHING
    elif current_price > line:
        relation = RelationToTrendline.ABOVE
    else:
        relation = RelationToTrendline.BELOW
    state = TrendState.ASCENDING_SUPPORTED if candidate.trendline_type is TrendlineType.ASCENDING else TrendState.DESCENDING_RESISTED
    return relation, state


def _result_from_candidate(candidate: _Candidate, completed: Sequence[Candle], current_price: Decimal, evaluated_at: datetime, config: TrendEngineConfig, *, candle_count: int, lookback_used: int, base_warnings: Sequence[str], stale: bool) -> TrendlineResult:
    line = _line_value(candidate.anchor_1, candidate.slope, evaluated_at)
    tolerance = _tolerance(config, candidate.anchor_1.timeframe, line, completed[-1] if completed else None)
    relation, state = _relation(candidate, completed, current_price, evaluated_at, config)
    status = DataStatus.STALE if stale else DataStatus.OK
    valid = candidate.valid and not stale
    if stale:
        state = TrendState.STALE
        relation = RelationToTrendline.INSUFFICIENT_DATA
    return TrendlineResult(
        candidate.anchor_1.timeframe, candidate.trendline_type, candidate.anchor_1, candidate.anchor_2,
        candidate.slope, line, current_price, current_price - line,
        (current_price - line) / line * Decimal("100") if line else None,
        relation, candidate.touch_count, candidate.violation_count, candidate.last_touch_at,
        candidate.anchor_2.timestamp, valid, candidate.score if valid else None, state, status,
        candle_count, lookback_used, evaluated_at, (*base_warnings, *candidate.warnings),
    )


def evaluate_trendline(timeframe: PositionTimeframe, candles: Sequence[Candle], current_price: object, evaluated_at: datetime, config: TrendEngineConfig) -> TrendlineResult:
    """Evaluate one independent timeframe; no directional decision is produced."""

    price = _decimal(current_price)
    if price is None or price <= 0:
        return _empty_result(timeframe, evaluated_at, DataStatus.INVALID, ("invalid_current_price",), candle_count=len(candles))
    prepared, warnings = _validate_and_prepare(candles, evaluated_at, config)
    if prepared is None:
        return _empty_result(timeframe, evaluated_at, DataStatus.INVALID, warnings, candle_count=len(candles), current_price=price)
    try:
        closed = [candle for candle in prepared if candle.end <= evaluated_at]
    except TypeError:
        return _empty_result(timeframe, evaluated_at, DataStatus.INVALID, ("incompatible_candle_timestamp",), candle_count=len(prepared), current_price=price)
    if len(closed) < config.minimum_closed_candles_by_timeframe[timeframe]:
        return _empty_result(timeframe, evaluated_at, DataStatus.INSUFFICIENT_DATA, (*warnings, "insufficient_closed_candles"), candle_count=len(prepared), current_price=price)
    sample = closed[-config.lookback_by_timeframe[timeframe]:]
    offset = len(closed) - len(sample)
    try:
        pivots = detect_confirmed_pivots(timeframe, sample, left_window=config.pivot_left_window_by_timeframe[timeframe], right_window=config.pivot_right_window_by_timeframe[timeframe], plateau_policy=config.plateau_policy, index_offset=offset)
        candidates = _build_candidates(timeframe, pivots, closed, evaluated_at, config)
        valid_candidates = [candidate for candidate in candidates if candidate.valid]
        latest_end = prepared[-1].end
        stale = evaluated_at - latest_end > config.stale_after_by_timeframe[timeframe]
        if not valid_candidates:
            broken = [candidate for candidate in candidates if candidate.break_index is not None]
            if broken:
                best_broken = max(broken, key=lambda item: item.score)
                return _result_from_candidate(best_broken, closed, price, evaluated_at, config, candle_count=len(prepared), lookback_used=len(sample), base_warnings=warnings, stale=stale)
            return _no_trendline_result(timeframe, evaluated_at, DataStatus.STALE if stale else DataStatus.OK,
                                        (*warnings, "no_valid_trendline"), candle_count=len(prepared),
                                        lookback_used=len(sample), current_price=price)
        ordered = sorted(valid_candidates, key=lambda item: item.score, reverse=True)
        if len(ordered) > 1 and ordered[0].score - ordered[1].score <= config.ambiguity_score_gap:
            return TrendlineResult(timeframe, TrendlineType.AMBIGUOUS, None, None, None, None, price, None, None,
                                   RelationToTrendline.AMBIGUOUS, 0, 0, None, None, False, None,
                                   TrendState.AMBIGUOUS, DataStatus.STALE if stale else DataStatus.OK,
                                   len(prepared), len(sample), evaluated_at, (*warnings, "candidate_score_ambiguous"))
        return _result_from_candidate(ordered[0], closed, price, evaluated_at, config, candle_count=len(prepared), lookback_used=len(sample), base_warnings=warnings, stale=stale)
    except (ArithmeticError, InvalidOperation, TypeError, ValueError) as error:
        return _empty_result(timeframe, evaluated_at, DataStatus.CALCULATION_ERROR,
                             (*warnings, f"calculation_error:{type(error).__name__}"), candle_count=len(prepared), current_price=price)


def evaluate_all_trendlines(candles_by_timeframe: Mapping[PositionTimeframe, Sequence[Candle]], current_price: object | Mapping[PositionTimeframe, object], evaluated_at: datetime, config: TrendEngineConfig) -> dict[PositionTimeframe, TrendlineResult]:
    """Return all fixed timeframes without allowing a single failure to crash the result."""

    results: dict[PositionTimeframe, TrendlineResult] = {}
    for timeframe in ALL_TIMEFRAMES:
        candles = candles_by_timeframe.get(timeframe, ())
        price = current_price.get(timeframe) if isinstance(current_price, Mapping) else current_price
        try:
            results[timeframe] = evaluate_trendline(timeframe, candles, price, evaluated_at, config)
        except Exception as error:  # defensive aggregation boundary with retained diagnostics
            results[timeframe] = _empty_result(timeframe, evaluated_at, DataStatus.CALCULATION_ERROR,
                                               (f"unexpected_calculation_error:{type(error).__name__}",), candle_count=len(candles))
    return results
