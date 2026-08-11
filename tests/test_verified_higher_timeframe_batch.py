from datetime import date, datetime, timedelta
from types import MappingProxyType
from zoneinfo import ZoneInfo

import pytest

from kam_market_ai.market_data.fubon_five_timeframe_pipeline import (
    FiveTimeframe,
    FiveTimeframeCandleResult,
    complete_with_verified_higher_timeframes,
)
from kam_market_ai.market_data.verified_higher_timeframe_batch import (
    ClassifiedSourceCandle,
    VerifiedCompletenessAttestation,
    certify_higher_timeframe_batch,
)
from kam_market_ai.models import Candle, Instrument

TAIPEI = ZoneInfo("Asia/Taipei")


def classified(day: date, hour: int, opening: float) -> ClassifiedSourceCandle:
    at = datetime.combine(day - timedelta(days=1), datetime.min.time(), TAIPEI).replace(hour=hour)
    candle = Candle(Instrument.TMF, at, at + timedelta(hours=1), opening, opening + 3, opening - 2, opening + 1, 10)
    return ClassifiedSourceCandle(candle, day, day - timedelta(days=day.weekday()))


def verified_batch():
    source = (
        classified(date(2026, 8, 10), 15, 100),
        classified(date(2026, 8, 10), 16, 101),
        classified(date(2026, 8, 11), 15, 103),
        classified(date(2026, 8, 11), 16, 104),
    )
    attestation = VerifiedCompletenessAttestation(
        (date(2026, 8, 10), date(2026, 8, 11)),
        (date(2026, 8, 10),),
    )
    return certify_higher_timeframe_batch(Instrument.TMF, source, attestation)


def test_explicit_attestation_produces_verified_day_and_week_batches() -> None:
    result = verified_batch()

    assert [day.trading_date for day in result.days] == [date(2026, 8, 10), date(2026, 8, 11)]
    assert len(result.day_candles) == 2
    assert len(result.week_candles) == 1
    assert (result.week_candles[0].open, result.week_candles[0].close) == (100, 105)
    assert result.status == "VERIFIED_COMPLETE_HIGHER_TIMEFRAMES"
    assert result.trading_enabled is False


def test_unattested_or_extra_trading_day_is_rejected() -> None:
    source = (classified(date(2026, 8, 10), 15, 100),)
    attestation = VerifiedCompletenessAttestation(
        (date(2026, 8, 10), date(2026, 8, 11)),
        (date(2026, 8, 10),),
    )
    with pytest.raises(ValueError, match="TRADING_DATE_ATTESTATION_MISMATCH"):
        certify_higher_timeframe_batch(Instrument.TMF, source, attestation)


def test_unattested_or_extra_trading_week_is_rejected() -> None:
    source = (classified(date(2026, 8, 10), 15, 100),)
    attestation = VerifiedCompletenessAttestation(
        (date(2026, 8, 10),),
        (date(2026, 8, 10), date(2026, 8, 17)),
    )
    with pytest.raises(ValueError, match="TRADING_WEEK_ATTESTATION_MISMATCH"):
        certify_higher_timeframe_batch(Instrument.TMF, source, attestation)


def test_verified_higher_batch_completes_canonical_five_timeframes() -> None:
    candle = classified(date(2026, 8, 10), 15, 100).candle
    partial = FiveTimeframeCandleResult(
        Instrument.TMF,
        "AFTERHOURS",
        MappingProxyType({
            FiveTimeframe.M5: (candle,),
            FiveTimeframe.M15: (candle,),
            FiveTimeframe.M60: (candle,),
        }),
        (FiveTimeframe.DAY, FiveTimeframe.WEEK),
        3,
    )

    result = complete_with_verified_higher_timeframes(partial, verified_batch())

    assert tuple(result.series) == tuple(FiveTimeframe)
    assert result.safe_payload()["status"] == "READY_VERIFIED_FIVE_TIMEFRAMES"
    assert result.safe_payload()["missing_timeframes"] == []
    assert result.safe_payload()["trading_enabled"] is False


def test_cross_instrument_completion_is_rejected() -> None:
    candle = Candle(Instrument.MTX, datetime.now(TAIPEI), datetime.now(TAIPEI) + timedelta(minutes=5), 1, 2, 1, 2, 1)
    partial = FiveTimeframeCandleResult(
        Instrument.MTX,
        "NORMAL",
        MappingProxyType({timeframe: (candle,) for timeframe in tuple(FiveTimeframe)[:3]}),
        (FiveTimeframe.DAY, FiveTimeframe.WEEK),
        3,
    )
    with pytest.raises(ValueError, match="INSTRUMENT_IDENTITY_MISMATCH"):
        complete_with_verified_higher_timeframes(partial, verified_batch())


def test_classified_trading_dates_cannot_move_backwards() -> None:
    early = classified(date(2026, 8, 10), 15, 100).candle
    later = classified(date(2026, 8, 11), 15, 101).candle
    source = (
        ClassifiedSourceCandle(early, date(2026, 8, 11), date(2026, 8, 10)),
        ClassifiedSourceCandle(later, date(2026, 8, 10), date(2026, 8, 10)),
    )
    attestation = VerifiedCompletenessAttestation(
        (date(2026, 8, 10), date(2026, 8, 11)),
        (date(2026, 8, 10),),
    )
    with pytest.raises(ValueError, match="TRADING_DATES_NOT_CHRONOLOGICAL"):
        certify_higher_timeframe_batch(Instrument.TMF, source, attestation)
