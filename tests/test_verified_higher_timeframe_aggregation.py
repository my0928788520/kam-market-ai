from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from kam_market_ai.market_data.verified_higher_timeframe_aggregation import (
    VerifiedTradingDay,
    VerifiedTradingWeek,
    aggregate_verified_day,
    aggregate_verified_week,
)
from kam_market_ai.models import Candle, Instrument

TAIPEI = ZoneInfo("Asia/Taipei")


def candle(at: datetime, opening: float, high: float, low: float, close: float, volume: int) -> Candle:
    return Candle(Instrument.TMF, at, at + timedelta(minutes=60), opening, high, low, close, volume)


def trading_day(day: date, prices: tuple[float, float, float], *, complete: bool = True) -> VerifiedTradingDay:
    start = datetime.combine(day - timedelta(days=1), datetime.min.time(), TAIPEI).replace(hour=15)
    first, middle, last = prices
    return VerifiedTradingDay(
        trading_date=day,
        week_start=day - timedelta(days=day.weekday()),
        candles=(
            candle(start, first, first + 3, first - 2, middle, 10),
            candle(start + timedelta(hours=1), middle, middle + 4, middle - 5, last, 20),
        ),
        complete=complete,
    )


def test_day_aggregation_uses_explicit_trading_identity_and_ohlcv() -> None:
    day = trading_day(date(2026, 8, 10), (100, 102, 99))

    result = aggregate_verified_day(day)

    assert (result.open, result.high, result.low, result.close, result.volume) == (100, 106, 97, 99, 30)
    assert result.start == day.candles[0].start
    assert result.end == day.candles[-1].end


def test_week_aggregation_uses_only_explicit_complete_trading_days() -> None:
    monday = trading_day(date(2026, 8, 10), (100, 102, 99))
    tuesday = trading_day(date(2026, 8, 11), (99, 105, 104))

    result = aggregate_verified_week(VerifiedTradingWeek(date(2026, 8, 10), (monday, tuesday), True))

    assert (result.open, result.high, result.low, result.close, result.volume) == (100, 109, 97, 104, 60)
    assert result.start == monday.candles[0].start
    assert result.end == tuesday.candles[-1].end


@pytest.mark.parametrize("complete", [False])
def test_incomplete_day_is_rejected_before_aggregation(complete: bool) -> None:
    with pytest.raises(ValueError, match="TRADING_DAY_NOT_COMPLETE"):
        trading_day(date(2026, 8, 10), (100, 102, 99), complete=complete)


def test_incomplete_week_is_rejected_before_aggregation() -> None:
    monday = trading_day(date(2026, 8, 10), (100, 102, 99))
    with pytest.raises(ValueError, match="TRADING_WEEK_NOT_COMPLETE"):
        VerifiedTradingWeek(date(2026, 8, 10), (monday,), False)


def test_week_identity_is_never_inferred_or_silently_rewritten() -> None:
    monday = trading_day(date(2026, 8, 10), (100, 102, 99))
    with pytest.raises(ValueError, match="WEEK_IDENTITY_MISMATCH"):
        VerifiedTradingWeek(date(2026, 8, 17), (monday,), True)
