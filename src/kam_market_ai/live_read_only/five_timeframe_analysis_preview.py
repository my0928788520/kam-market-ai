"""Read-only analysis preview for verified five-timeframe candles.

All five verified candle slices are evaluated with centralized provisional
parameters.  This boundary never turns provisional analysis into a trading
decision.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from kam_market_ai.analysis.position_engine import (
    PositionEngineConfig,
    PositionTimeframe,
    evaluate_all_position_ranges,
)
from kam_market_ai.analysis.structure_engine import (
    StructureEngineConfig,
    evaluate_all_structures,
)
from kam_market_ai.analysis.timing_engine import (
    TimingEngineConfig,
    evaluate_all_timings,
)
from kam_market_ai.analysis.trend_engine import (
    TrendEngineConfig,
    evaluate_all_trendlines,
)
from kam_market_ai.decision.decision_contract import (
    DecisionInputConfig,
    build_decision_input_contract,
)
from kam_market_ai.market_data.fubon_five_timeframe_pipeline import (
    CompleteFiveTimeframeCandleResult,
    FiveTimeframe,
)

_ENGINE_TIMEFRAMES = {
    FiveTimeframe.M5: PositionTimeframe.M5,
    FiveTimeframe.M15: PositionTimeframe.M15,
    FiveTimeframe.M60: PositionTimeframe.M60,
    FiveTimeframe.DAY: PositionTimeframe.D1,
    FiveTimeframe.WEEK: PositionTimeframe.W1,
}


@dataclass(frozen=True, slots=True)
class VerifiedFiveTimeframeAnalysisPreview:
    evaluated_at: datetime
    overall_status: str
    timeframe_analysis: dict[str, dict[str, object]]
    blockers: tuple[str, ...]
    decision_status: str = "BLOCKED"
    action: str = "HOLD"
    market_data_only: bool = True
    live_order_allowed: bool = False

    def safe_payload(self) -> dict[str, object]:
        return {
            "success": False,
            "analysis_status": self.overall_status,
            "evaluated_at": self.evaluated_at.isoformat(),
            "decision_status": self.decision_status,
            "action": self.action,
            "blockers": list(self.blockers),
            "timeframes": self.timeframe_analysis,
            "market_data_only": self.market_data_only,
            "live_order_allowed": self.live_order_allowed,
            "raw_candles_retained": False,
        }


def build_verified_five_timeframe_analysis_preview(
    value: CompleteFiveTimeframeCandleResult,
    *,
    evaluated_at: datetime,
) -> VerifiedFiveTimeframeAnalysisPreview:
    """Run all five analysis slices while keeping decisions fail-closed."""
    if not isinstance(value, CompleteFiveTimeframeCandleResult):
        raise TypeError("CompleteFiveTimeframeCandleResult is required")
    if evaluated_at.tzinfo is None or evaluated_at.utcoffset() is None:
        raise ValueError("evaluated_at must be timezone-aware")

    candles = {
        engine: value.series[source]
        for source, engine in _ENGINE_TIMEFRAMES.items()
    }
    current_prices = {
        engine: series[-1].close
        for engine, series in candles.items()
    }
    position = evaluate_all_position_ranges(
        candles,
        current_prices,
        evaluated_at,
        PositionEngineConfig.provisional(),
    )
    trend = evaluate_all_trendlines(
        candles,
        current_prices,
        evaluated_at,
        TrendEngineConfig.provisional(),
    )
    structure = evaluate_all_structures(
        candles,
        current_prices,
        evaluated_at,
        StructureEngineConfig.provisional(),
    )
    timing = evaluate_all_timings(
        candles,
        evaluated_at,
        TimingEngineConfig.provisional(),
    )
    contract = build_decision_input_contract(
        position,
        trend,
        structure,
        timing,
        evaluated_at,
        DecisionInputConfig.provisional(),
    )

    analysis: dict[str, dict[str, object]] = {}
    for source, engine in _ENGINE_TIMEFRAMES.items():
        frame = contract.timeframes[engine]
        analysis[source.value] = {
            "status": frame.input_status.value,
            "usable": frame.usable,
            "position": frame.position.normalized_state.value,
            "trend": frame.trend.normalized_state.value,
            "structure": frame.structure.normalized_state.value,
            "timing": frame.timing.normalized_state.value,
            "error_codes": list(frame.error_codes),
        }

    blockers: list[str] = []
    if contract.overall_status.value != "ready":
        blockers.append("ANALYSIS_INPUT_NOT_READY")
    blockers.append("TRADING_DECISION_MAPPING_NOT_APPROVED")
    return VerifiedFiveTimeframeAnalysisPreview(
        evaluated_at=evaluated_at,
        overall_status=contract.overall_status.value,
        timeframe_analysis=analysis,
        blockers=tuple(blockers),
    )


__all__ = [
    "VerifiedFiveTimeframeAnalysisPreview",
    "build_verified_five_timeframe_analysis_preview",
]
