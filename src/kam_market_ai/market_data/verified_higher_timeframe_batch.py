"""Upstream-attested source batches for safe day/week candle production.

The batch boundary validates explicit trading-day and trading-week identities.
It never derives either identity, completeness, or holiday status from candle
timestamps.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from itertools import pairwise

from kam_market_ai.models import Candle, Instrument

from .verified_higher_timeframe_aggregation import (
    VerifiedTradingDay,
    VerifiedTradingWeek,
    aggregate_verified_day,
    aggregate_verified_week,
)


@dataclass(frozen=True, slots=True)
class ClassifiedSourceCandle:
    candle: Candle
    trading_date: date
    week_start: date

    def __post_init__(self) -> None:
        if self.week_start.weekday() != 0 or not self.week_start <= self.trading_date:
            raise ValueError("BATCH_INVALID_VERIFIED_WEEK_START")


@dataclass(frozen=True, slots=True)
class VerifiedCompletenessAttestation:
    complete_trading_dates: tuple[date, ...]
    complete_week_starts: tuple[date, ...]

    def __post_init__(self) -> None:
        if not self.complete_trading_dates:
            raise ValueError("BATCH_COMPLETE_TRADING_DATES_REQUIRED")
        if not self.complete_week_starts:
            raise ValueError("BATCH_COMPLETE_WEEK_STARTS_REQUIRED")
        if any(current <= previous for previous, current in pairwise(self.complete_trading_dates)):
            raise ValueError("BATCH_TRADING_DATES_NOT_STRICTLY_CHRONOLOGICAL")
        if any(day.weekday() != 0 for day in self.complete_week_starts):
            raise ValueError("BATCH_INVALID_VERIFIED_WEEK_START")
        if any(current <= previous for previous, current in pairwise(self.complete_week_starts)):
            raise ValueError("BATCH_WEEK_STARTS_NOT_STRICTLY_CHRONOLOGICAL")


@dataclass(frozen=True, slots=True)
class VerifiedHigherTimeframeBatchResult:
    instrument: Instrument
    days: tuple[VerifiedTradingDay, ...]
    weeks: tuple[VerifiedTradingWeek, ...]
    day_candles: tuple[Candle, ...]
    week_candles: tuple[Candle, ...]
    status: str = "VERIFIED_COMPLETE_HIGHER_TIMEFRAMES"
    market_data_only: bool = True
    trading_enabled: bool = False

    def __post_init__(self) -> None:
        if not self.days or not self.weeks or not self.day_candles or not self.week_candles:
            raise ValueError("BATCH_VERIFIED_DAY_AND_WEEK_OUTPUT_REQUIRED")
        if len(self.days) != len(self.day_candles) or len(self.weeks) != len(self.week_candles):
            raise ValueError("BATCH_AGGREGATE_COUNT_MISMATCH")
        if any(candle.instrument is not self.instrument for candle in (*self.day_candles, *self.week_candles)):
            raise ValueError("BATCH_MIXED_INSTRUMENTS")
        if self.status != "VERIFIED_COMPLETE_HIGHER_TIMEFRAMES":
            raise ValueError("BATCH_INVALID_VERIFIED_STATUS")
        if not self.market_data_only or self.trading_enabled:
            raise ValueError("BATCH_MARKET_DATA_ONLY_BOUNDARY_REQUIRED")


def certify_higher_timeframe_batch(
    instrument: Instrument,
    source: tuple[ClassifiedSourceCandle, ...],
    attestation: VerifiedCompletenessAttestation,
) -> VerifiedHigherTimeframeBatchResult:
    """Validate an explicit upstream attestation and produce closed day/week bars."""
    if instrument not in {Instrument.TX, Instrument.MTX, Instrument.TMF}:
        raise ValueError("BATCH_UNSUPPORTED_FUTURES_INSTRUMENT")
    if not source:
        raise ValueError("BATCH_CLASSIFIED_SOURCE_REQUIRED")
    if any(item.candle.instrument is not instrument for item in source):
        raise ValueError("BATCH_MIXED_INSTRUMENTS")
    if any(current.candle.start < previous.candle.end for previous, current in pairwise(source)):
        raise ValueError("BATCH_SOURCE_NOT_CHRONOLOGICAL")
    if any(current.trading_date < previous.trading_date for previous, current in pairwise(source)):
        raise ValueError("BATCH_TRADING_DATES_NOT_CHRONOLOGICAL")

    by_day: dict[date, list[Candle]] = defaultdict(list)
    week_for_day: dict[date, date] = {}
    for item in source:
        previous_week = week_for_day.setdefault(item.trading_date, item.week_start)
        if previous_week != item.week_start:
            raise ValueError("BATCH_TRADING_DATE_WEEK_IDENTITY_CONFLICT")
        by_day[item.trading_date].append(item.candle)

    attested_dates = set(attestation.complete_trading_dates)
    if set(by_day) != attested_dates:
        raise ValueError("BATCH_TRADING_DATE_ATTESTATION_MISMATCH")

    days = tuple(
        VerifiedTradingDay(day, week_for_day[day], tuple(by_day[day]), True)
        for day in attestation.complete_trading_dates
    )
    by_week: dict[date, list[VerifiedTradingDay]] = defaultdict(list)
    for day in days:
        by_week[day.week_start].append(day)
    if set(by_week) != set(attestation.complete_week_starts):
        raise ValueError("BATCH_TRADING_WEEK_ATTESTATION_MISMATCH")

    weeks = tuple(
        VerifiedTradingWeek(week_start, tuple(by_week[week_start]), True)
        for week_start in attestation.complete_week_starts
    )
    return VerifiedHigherTimeframeBatchResult(
        instrument=instrument,
        days=days,
        weeks=weeks,
        day_candles=tuple(aggregate_verified_day(day) for day in days),
        week_candles=tuple(aggregate_verified_week(week) for week in weeks),
    )


__all__ = [
    "ClassifiedSourceCandle",
    "VerifiedCompletenessAttestation",
    "VerifiedHigherTimeframeBatchResult",
    "certify_higher_timeframe_batch",
]
