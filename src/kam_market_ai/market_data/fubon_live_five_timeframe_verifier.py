"""One-shot live TMF five-timeframe verification with explicit attestations."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from kam_market_ai.live_read_only.five_timeframe_analysis_preview import (
    build_verified_five_timeframe_analysis_preview,
)
from kam_market_ai.models import Instrument

from .fubon_five_timeframe_pipeline import (
    FiveTimeframe,
    FubonFiveTimeframeCandlePipeline,
    complete_with_verified_higher_timeframes,
)
from .verified_higher_timeframe_batch import (
    ClassifiedSourceCandle,
    VerifiedCompletenessAttestation,
    certify_higher_timeframe_batch,
)


@dataclass(frozen=True, slots=True)
class CandleClassification:
    candle_start: datetime
    trading_date: date
    week_start: date

    def __post_init__(self) -> None:
        if self.candle_start.tzinfo is None:
            raise ValueError("LIVE_VERIFIER_TIMEZONE_REQUIRED")
        if self.week_start.weekday() != 0 or self.week_start > self.trading_date:
            raise ValueError("LIVE_VERIFIER_INVALID_WEEK_START")


class FubonLiveFiveTimeframeVerifier:
    """Fetch exactly three TMF slices and fail closed without full attestation."""

    def __init__(self, pipeline: FubonFiveTimeframeCandlePipeline) -> None:
        if not isinstance(pipeline, FubonFiveTimeframeCandlePipeline):
            raise TypeError("FubonFiveTimeframeCandlePipeline is required")
        self._pipeline = pipeline
        self._latest_candle_result = None

    @property
    def latest_candle_result(self):
        """Latest immutable result for local read-only chart rendering only."""
        return self._latest_candle_result

    def run(
        self,
        *,
        symbol: str,
        session: str | None,
        after_hours: bool = False,
        classifications: tuple[CandleClassification, ...] = (),
        complete_trading_dates: tuple[date, ...] = (),
        complete_week_starts: tuple[date, ...] = (),
        verified_at: datetime | None = None,
    ) -> dict[str, object]:
        if not symbol or symbol.strip() != symbol:
            raise ValueError("LIVE_VERIFIER_VERIFIED_SYMBOL_REQUIRED")
        partial = self._pipeline.run(
            Instrument.TMF,
            session=session,
            after_hours=after_hours,
        )
        self._latest_candle_result = partial
        source = partial.series[FiveTimeframe.M60]
        starts = tuple(candle.start for candle in source)
        base = {
            **partial.safe_payload(),
            "success": False,
            "status": "ATTESTATION_REQUIRED",
            "source_kind": "FUBON_LIVE_INTRADAY_CANDLES",
            "symbol": symbol,
            "source_timeframe": "60m",
            "source_candle_starts": [item.isoformat() for item in starts],
            "source_candle_count": len(starts),
            "external_endpoint_call_count": 3,
            "credentials_loaded": True,
            "account_connected": False,
            "broker_connected": False,
            "live_order_allowed": False,
        }
        if not classifications and not complete_trading_dates and not complete_week_starts:
            analysis_preview = build_verified_five_timeframe_analysis_preview(
                partial,
                evaluated_at=datetime.now(UTC),
            ).safe_payload()
            base["analysis_preview"] = analysis_preview
            base["decision_preview"] = analysis_preview["kam_rule_decision"]
            return base
        if not classifications or not complete_trading_dates or not complete_week_starts:
            raise ValueError("LIVE_VERIFIER_COMPLETE_ATTESTATION_REQUIRED")
        observed_at = verified_at or datetime.now(UTC)
        if observed_at.tzinfo is None or observed_at.utcoffset() is None:
            raise ValueError("LIVE_VERIFIER_VERIFIED_AT_TIMEZONE_REQUIRED")
        local_date = observed_at.astimezone(ZoneInfo("Asia/Taipei")).date()
        if any(item >= local_date for item in complete_trading_dates):
            raise ValueError("LIVE_VERIFIER_CURRENT_TRADING_DATE_CANNOT_BE_COMPLETE")
        if any(item + timedelta(days=7) > local_date for item in complete_week_starts):
            raise ValueError("LIVE_VERIFIER_CURRENT_TRADING_WEEK_CANNOT_BE_COMPLETE")
        by_start = {item.candle_start: item for item in classifications}
        if len(by_start) != len(classifications):
            raise ValueError("LIVE_VERIFIER_DUPLICATE_CLASSIFICATION")
        if set(by_start) != set(starts):
            raise ValueError("LIVE_VERIFIER_CLASSIFICATION_COVERAGE_MISMATCH")
        classified = tuple(
            ClassifiedSourceCandle(
                candle,
                by_start[candle.start].trading_date,
                by_start[candle.start].week_start,
            )
            for candle in source
        )
        attestation = VerifiedCompletenessAttestation(
            complete_trading_dates,
            complete_week_starts,
        )
        complete = complete_with_verified_higher_timeframes(
            partial,
            certify_higher_timeframe_batch(Instrument.TMF, classified, attestation),
        )
        self._latest_candle_result = complete
        payload = complete.safe_payload()
        payload.update({
            "source_kind": "FUBON_LIVE_INTRADAY_CANDLES",
            "symbol": symbol,
            "source_timeframe": "60m",
            "source_candle_starts": [item.isoformat() for item in starts],
            "source_candle_count": len(starts),
            "external_endpoint_call_count": 3,
            "verified_trading_dates": [item.isoformat() for item in complete_trading_dates],
            "verified_week_starts": [item.isoformat() for item in complete_week_starts],
            "credentials_loaded": True,
            "account_connected": False,
            "broker_connected": False,
            "live_order_allowed": False,
        })
        analysis_preview = build_verified_five_timeframe_analysis_preview(
            complete,
            evaluated_at=datetime.now(UTC),
        ).safe_payload()
        payload["analysis_preview"] = analysis_preview
        payload["decision_preview"] = analysis_preview["kam_rule_decision"]
        return payload


__all__ = ["CandleClassification", "FubonLiveFiveTimeframeVerifier"]
