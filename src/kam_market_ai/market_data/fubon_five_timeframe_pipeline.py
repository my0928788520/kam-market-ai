"""Manual, market-data-only bridge toward KAM's five-timeframe pipeline.

Fubon intraday candles officially cover minute intervals only.  This bridge
therefore loads the verified 5m/15m/60m slices and keeps day/week explicitly
blocked until an official source or an approved session-aware aggregation
contract exists.  It never presents partial coverage as a ready five-frame
dataset.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType

from kam_market_ai.models import Candle, Instrument

from .fubon_neo import FubonIntradayCandlesAdapter, OfficialIntradayCandleSpec
from .verified_higher_timeframe_batch import VerifiedHigherTimeframeBatchResult


class FiveTimeframe(StrEnum):
    M5 = "5m"
    M15 = "15m"
    M60 = "60m"
    DAY = "1d"
    WEEK = "1w"


REQUIRED_FIVE_TIMEFRAMES = (
    FiveTimeframe.M5,
    FiveTimeframe.M15,
    FiveTimeframe.M60,
    FiveTimeframe.DAY,
    FiveTimeframe.WEEK,
)
VERIFIED_INTRADAY_SPECS: Mapping[FiveTimeframe, OfficialIntradayCandleSpec] = MappingProxyType(
    {
        FiveTimeframe.M5: OfficialIntradayCandleSpec("VERIFIED_AT_RUNTIME", "5", 5),
        FiveTimeframe.M15: OfficialIntradayCandleSpec("VERIFIED_AT_RUNTIME", "15", 15),
        FiveTimeframe.M60: OfficialIntradayCandleSpec("VERIFIED_AT_RUNTIME", "60", 60),
    }
)


@dataclass(frozen=True, slots=True)
class FiveTimeframeCandleResult:
    instrument: Instrument
    session: str
    series: Mapping[FiveTimeframe, tuple[Candle, ...]]
    missing_timeframes: tuple[FiveTimeframe, ...]
    endpoint_call_count: int
    status: str = "BLOCKED_INCOMPLETE_COVERAGE"
    market_data_only: bool = True
    manual_trigger_only: bool = True
    trading_enabled: bool = False
    raw_payload_retained: bool = False

    def __post_init__(self) -> None:
        if tuple(self.series) != REQUIRED_FIVE_TIMEFRAMES[:3]:
            raise ValueError("verified intraday series must be canonical 5m/15m/60m")
        if self.missing_timeframes != REQUIRED_FIVE_TIMEFRAMES[3:]:
            raise ValueError("day/week coverage must remain explicitly missing")
        if self.endpoint_call_count != len(self.series):
            raise ValueError("endpoint call count must match fetched intraday series")
        if any(not values for values in self.series.values()):
            raise ValueError("empty intraday series cannot enter the five-timeframe bridge")
        if self.status != "BLOCKED_INCOMPLETE_COVERAGE":
            raise ValueError("partial five-timeframe coverage cannot be READY")

    def safe_payload(self) -> dict[str, object]:
        return {
            "success": True,
            "status": self.status,
            "instrument": self.instrument.value,
            "session": self.session,
            "required_timeframes": [item.value for item in REQUIRED_FIVE_TIMEFRAMES],
            "loaded_timeframes": [item.value for item in self.series],
            "missing_timeframes": [item.value for item in self.missing_timeframes],
            "candle_counts": {item.value: len(values) for item, values in self.series.items()},
            "endpoint_call_count": self.endpoint_call_count,
            "market_data_only": self.market_data_only,
            "manual_trigger_only": self.manual_trigger_only,
            "trading_enabled": self.trading_enabled,
            "raw_payload_retained": self.raw_payload_retained,
        }


@dataclass(frozen=True, slots=True)
class CompleteFiveTimeframeCandleResult:
    instrument: Instrument
    session: str
    series: Mapping[FiveTimeframe, tuple[Candle, ...]]
    endpoint_call_count: int
    status: str = "READY_VERIFIED_FIVE_TIMEFRAMES"
    market_data_only: bool = True
    manual_trigger_only: bool = True
    trading_enabled: bool = False
    raw_payload_retained: bool = False

    def __post_init__(self) -> None:
        if tuple(self.series) != REQUIRED_FIVE_TIMEFRAMES:
            raise ValueError("complete five-timeframe series must be canonical")
        if any(not values for values in self.series.values()):
            raise ValueError("complete five-timeframe series cannot contain empty slices")
        if any(
            candle.instrument is not self.instrument
            for values in self.series.values()
            for candle in values
        ):
            raise ValueError("complete five-timeframe series cannot mix instruments")
        if self.endpoint_call_count != 3:
            raise ValueError("complete five-timeframe result requires three intraday endpoint calls")
        if self.status != "READY_VERIFIED_FIVE_TIMEFRAMES":
            raise ValueError("complete five-timeframe result requires verified READY status")
        if (
            not self.market_data_only
            or not self.manual_trigger_only
            or self.trading_enabled
            or self.raw_payload_retained
        ):
            raise ValueError("complete five-timeframe result violates read-only boundary")

    def safe_payload(self) -> dict[str, object]:
        return {
            "success": True,
            "status": self.status,
            "instrument": self.instrument.value,
            "session": self.session,
            "required_timeframes": [item.value for item in REQUIRED_FIVE_TIMEFRAMES],
            "loaded_timeframes": [item.value for item in self.series],
            "missing_timeframes": [],
            "candle_counts": {item.value: len(values) for item, values in self.series.items()},
            "endpoint_call_count": self.endpoint_call_count,
            "market_data_only": self.market_data_only,
            "manual_trigger_only": self.manual_trigger_only,
            "trading_enabled": self.trading_enabled,
            "raw_payload_retained": self.raw_payload_retained,
        }


def complete_with_verified_higher_timeframes(
    partial: FiveTimeframeCandleResult,
    higher: VerifiedHigherTimeframeBatchResult,
) -> CompleteFiveTimeframeCandleResult:
    """Join minute slices only with an independently verified day/week batch."""
    if not isinstance(partial, FiveTimeframeCandleResult):
        raise TypeError("FiveTimeframeCandleResult is required")
    if not isinstance(higher, VerifiedHigherTimeframeBatchResult):
        raise TypeError("VerifiedHigherTimeframeBatchResult is required")
    if partial.instrument is not higher.instrument:
        raise ValueError("FIVE_TIMEFRAME_INSTRUMENT_IDENTITY_MISMATCH")
    series = dict(partial.series)
    series[FiveTimeframe.DAY] = higher.day_candles
    series[FiveTimeframe.WEEK] = higher.week_candles
    return CompleteFiveTimeframeCandleResult(
        instrument=partial.instrument,
        session=partial.session,
        series=MappingProxyType(series),
        endpoint_call_count=partial.endpoint_call_count,
    )


class FubonFiveTimeframeCandlePipeline:
    """Fetch only the three officially supported KAM minute slices on demand."""

    def __init__(self, adapter: FubonIntradayCandlesAdapter) -> None:
        if not isinstance(adapter, FubonIntradayCandlesAdapter):
            raise TypeError("FubonIntradayCandlesAdapter is required")
        self._adapter = adapter

    def run(
        self,
        instrument: Instrument,
        *,
        session: str,
        after_hours: bool = False,
    ) -> FiveTimeframeCandleResult:
        if instrument not in {Instrument.TX, Instrument.MTX, Instrument.TMF}:
            raise ValueError("five-timeframe futures bridge supports TX, MTX, or TMF only")
        if not session or session.strip() != session:
            raise ValueError("verified official session token is required")
        series: dict[FiveTimeframe, tuple[Candle, ...]] = {}
        for timeframe in REQUIRED_FIVE_TIMEFRAMES[:3]:
            verified = VERIFIED_INTRADAY_SPECS[timeframe]
            spec = OfficialIntradayCandleSpec(session, verified.timeframe, verified.interval_minutes)
            candles = self._adapter.fetch(instrument, spec, after_hours=after_hours)
            if not candles:
                raise ValueError(f"FIVE_TIMEFRAME_EMPTY_{timeframe.value.upper()}")
            series[timeframe] = tuple(candles)
        return FiveTimeframeCandleResult(
            instrument=instrument,
            session=session,
            series=MappingProxyType(series),
            missing_timeframes=REQUIRED_FIVE_TIMEFRAMES[3:],
            endpoint_call_count=len(series),
        )


__all__ = [
    "REQUIRED_FIVE_TIMEFRAMES",
    "VERIFIED_INTRADAY_SPECS",
    "CompleteFiveTimeframeCandleResult",
    "FiveTimeframe",
    "FiveTimeframeCandleResult",
    "FubonFiveTimeframeCandlePipeline",
    "complete_with_verified_higher_timeframes",
]
