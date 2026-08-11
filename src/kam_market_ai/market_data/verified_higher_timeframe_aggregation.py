"""Fail-closed day/week aggregation from explicitly classified closed candles.

This module deliberately does not derive a trading date from a timestamp and
does not own a holiday calendar.  The upstream market-calendar boundary must
classify every source candle and attest that each trading day/week is complete.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from itertools import pairwise

from kam_market_ai.models import Candle


@dataclass(frozen=True, slots=True)
class VerifiedTradingDay:
    trading_date: date
    week_start: date
    candles: tuple[Candle, ...]
    complete: bool

    def __post_init__(self) -> None:
        if self.week_start.weekday() != 0 or not self.week_start <= self.trading_date:
            raise ValueError("AGGREGATION_INVALID_VERIFIED_WEEK_START")
        if not self.complete:
            raise ValueError("AGGREGATION_TRADING_DAY_NOT_COMPLETE")
        if not self.candles:
            raise ValueError("AGGREGATION_TRADING_DAY_EMPTY")
        instrument = self.candles[0].instrument
        if any(candle.instrument is not instrument for candle in self.candles):
            raise ValueError("AGGREGATION_MIXED_INSTRUMENTS")
        if any(current.start < previous.end for previous, current in pairwise(self.candles)):
            raise ValueError("AGGREGATION_SOURCE_NOT_CHRONOLOGICAL")


@dataclass(frozen=True, slots=True)
class VerifiedTradingWeek:
    week_start: date
    days: tuple[VerifiedTradingDay, ...]
    complete: bool

    def __post_init__(self) -> None:
        if self.week_start.weekday() != 0:
            raise ValueError("AGGREGATION_INVALID_VERIFIED_WEEK_START")
        if not self.complete:
            raise ValueError("AGGREGATION_TRADING_WEEK_NOT_COMPLETE")
        if not self.days:
            raise ValueError("AGGREGATION_TRADING_WEEK_EMPTY")
        if any(day.week_start != self.week_start for day in self.days):
            raise ValueError("AGGREGATION_WEEK_IDENTITY_MISMATCH")
        if any(current.trading_date <= previous.trading_date for previous, current in pairwise(self.days)):
            raise ValueError("AGGREGATION_DAYS_NOT_CHRONOLOGICAL")
        instrument = self.days[0].candles[0].instrument
        if any(day.candles[0].instrument is not instrument for day in self.days):
            raise ValueError("AGGREGATION_MIXED_INSTRUMENTS")


def _aggregate(candles: tuple[Candle, ...]) -> Candle:
    first, last = candles[0], candles[-1]
    return Candle(
        instrument=first.instrument,
        start=first.start,
        end=last.end,
        open=first.open,
        high=max(candle.high for candle in candles),
        low=min(candle.low for candle in candles),
        close=last.close,
        volume=sum(candle.volume for candle in candles),
    )


def aggregate_verified_day(day: VerifiedTradingDay) -> Candle:
    """Aggregate one upstream-attested, complete trading day."""
    if not isinstance(day, VerifiedTradingDay):
        raise TypeError("VerifiedTradingDay is required")
    return _aggregate(day.candles)


def aggregate_verified_week(week: VerifiedTradingWeek) -> Candle:
    """Aggregate one upstream-attested, complete trading week."""
    if not isinstance(week, VerifiedTradingWeek):
        raise TypeError("VerifiedTradingWeek is required")
    return _aggregate(tuple(aggregate_verified_day(day) for day in week.days))


__all__ = [
    "VerifiedTradingDay",
    "VerifiedTradingWeek",
    "aggregate_verified_day",
    "aggregate_verified_week",
]
