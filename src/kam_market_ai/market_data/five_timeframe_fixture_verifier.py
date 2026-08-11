"""One-shot offline verification of the complete five-timeframe contract."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from types import MappingProxyType
from zoneinfo import ZoneInfo

from kam_market_ai.models import Candle, Instrument

from .fubon_five_timeframe_pipeline import (
    FiveTimeframe,
    FiveTimeframeCandleResult,
    complete_with_verified_higher_timeframes,
)
from .verified_higher_timeframe_batch import (
    ClassifiedSourceCandle,
    VerifiedCompletenessAttestation,
    certify_higher_timeframe_batch,
)

FIXTURE_ID = "kam-five-timeframe-controlled-fixture-v1"
TAIPEI = ZoneInfo("Asia/Taipei")


@dataclass(frozen=True, slots=True)
class ControlledFixtureVerification:
    payload: dict[str, object]

    def __post_init__(self) -> None:
        if self.payload.get("status") != "READY_VERIFIED_FIVE_TIMEFRAMES":
            raise ValueError("FIXTURE_VERIFICATION_READY_STATUS_REQUIRED")


def _candle(start: datetime, minutes: int, opening: float) -> Candle:
    return Candle(
        Instrument.TMF,
        start,
        start + timedelta(minutes=minutes),
        opening,
        opening + 3,
        opening - 2,
        opening + 1,
        10,
    )


def run_controlled_fixture_verification() -> ControlledFixtureVerification:
    """Build and verify fixed local data without loading clients or external files."""
    first = datetime(2026, 8, 9, 15, tzinfo=TAIPEI)
    intraday = MappingProxyType({
        FiveTimeframe.M5: (_candle(first, 5, 100), _candle(first + timedelta(minutes=5), 5, 101)),
        FiveTimeframe.M15: (_candle(first, 15, 100), _candle(first + timedelta(minutes=15), 15, 102)),
        FiveTimeframe.M60: (_candle(first, 60, 100), _candle(first + timedelta(hours=1), 60, 103)),
    })
    partial = FiveTimeframeCandleResult(
        Instrument.TMF,
        "CONTROLLED_FIXTURE",
        intraday,
        (FiveTimeframe.DAY, FiveTimeframe.WEEK),
        3,
    )
    classified = (
        ClassifiedSourceCandle(_candle(first, 60, 100), date(2026, 8, 10), date(2026, 8, 10)),
        ClassifiedSourceCandle(_candle(first + timedelta(hours=1), 60, 103), date(2026, 8, 10), date(2026, 8, 10)),
        ClassifiedSourceCandle(_candle(first + timedelta(days=1), 60, 105), date(2026, 8, 11), date(2026, 8, 10)),
        ClassifiedSourceCandle(_candle(first + timedelta(days=1, hours=1), 60, 107), date(2026, 8, 11), date(2026, 8, 10)),
    )
    attestation = VerifiedCompletenessAttestation(
        (date(2026, 8, 10), date(2026, 8, 11)),
        (date(2026, 8, 10),),
    )
    complete = complete_with_verified_higher_timeframes(
        partial,
        certify_higher_timeframe_batch(Instrument.TMF, classified, attestation),
    )
    payload = complete.safe_payload()
    payload.update({
        "source_kind": "CONTROLLED_FIXTURE",
        "fixture_id": FIXTURE_ID,
        "external_endpoint_call_count": 0,
        "fixture_intraday_slice_count": 3,
        "verified_trading_dates": [item.isoformat() for item in attestation.complete_trading_dates],
        "verified_week_starts": [item.isoformat() for item in attestation.complete_week_starts],
        "coverage": {
            timeframe.value: {
                "count": len(candles),
                "first_start": candles[0].start.isoformat(),
                "last_end": candles[-1].end.isoformat(),
            }
            for timeframe, candles in complete.series.items()
        },
        "network_accessed": False,
        "credentials_loaded": False,
        "account_connected": False,
        "broker_connected": False,
        "live_order_allowed": False,
    })
    return ControlledFixtureVerification(payload)


__all__ = ["FIXTURE_ID", "ControlledFixtureVerification", "run_controlled_fixture_verification"]
