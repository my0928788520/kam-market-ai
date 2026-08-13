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
from kam_market_ai.decision.decision_confidence import (
    DecisionConfidenceConfig,
    evaluate_decision_confidence,
)
from kam_market_ai.decision.next_step_engine import (
    NextStepEngineConfig,
    evaluate_next_step,
)
from kam_market_ai.decision.risk_engine import RiskEngineConfig, evaluate_risk
from kam_market_ai.market_data.fubon_five_timeframe_pipeline import (
    CompleteFiveTimeframeCandleResult,
    FiveTimeframe,
    FiveTimeframeCandleResult,
)
from kam_market_ai.models import Candle
from .five_timeframe_kam_rule_bridge import (
    KAM_STATE_MAPPING_VERSION,
    evaluate_five_timeframe_kam_rules,
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
    decision_diagnostics: dict[str, object]
    three_second_summary: dict[str, object]
    kam_rule_decision: dict[str, object]
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
            "decision_diagnostics": self.decision_diagnostics,
            "three_second_summary": self.three_second_summary,
            "kam_rule_decision": self.kam_rule_decision,
            "market_data_only": self.market_data_only,
            "live_order_allowed": self.live_order_allowed,
            "raw_candles_retained": False,
        }


def build_verified_five_timeframe_analysis_preview(
    value: CompleteFiveTimeframeCandleResult | FiveTimeframeCandleResult,
    *,
    evaluated_at: datetime,
) -> VerifiedFiveTimeframeAnalysisPreview:
    """Run five analysis slices while distinguishing verified and forming bars."""
    if not isinstance(value, (CompleteFiveTimeframeCandleResult, FiveTimeframeCandleResult)):
        raise TypeError("five-timeframe candle result is required")
    if evaluated_at.tzinfo is None or evaluated_at.utcoffset() is None:
        raise ValueError("evaluated_at must be timezone-aware")

    provisional = isinstance(value, FiveTimeframeCandleResult)
    series = dict(value.series)
    if provisional:
        source = series[FiveTimeframe.M60]
        first, last = source[0], source[-1]
        forming = Candle(
            instrument=first.instrument,
            start=first.start,
            end=last.end,
            open=first.open,
            high=max(item.high for item in source),
            low=min(item.low for item in source),
            close=last.close,
            volume=sum(item.volume for item in source),
        )
        series[FiveTimeframe.DAY] = (forming,)
        series[FiveTimeframe.WEEK] = (forming,)
    candles = {
        engine: series[source]
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
    confidence = evaluate_decision_confidence(
        contract,
        DecisionConfidenceConfig.provisional(),
    )
    risk = evaluate_risk(contract, confidence, RiskEngineConfig.provisional())
    next_step = evaluate_next_step(
        contract,
        confidence,
        risk,
        NextStepEngineConfig.provisional(),
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
    if provisional:
        blockers.append("CURRENT_DAY_WEEK_BARS_ARE_PROVISIONAL")
    if contract.overall_status.value != "ready":
        blockers.append("ANALYSIS_INPUT_NOT_READY")
    mapped_states, kam_decision = evaluate_five_timeframe_kam_rules(analysis)
    blockers.extend(kam_decision.blockers)
    diagnostics: dict[str, object] = {
        "direction": confidence.overall_direction.value,
        "confidence_score": str(confidence.overall_confidence_score),
        "confidence_state": confidence.overall_confidence_state.value,
        "alignment_state": confidence.alignment_state.value,
        "risk_score": str(risk.overall_risk_score),
        "risk_level": risk.overall_risk_level.value,
        "risk_state": risk.operational_state.value,
        "next_step": next_step.next_step.value,
        "next_step_state": next_step.operational_state.value,
        "next_step_priority": next_step.priority.value,
        "observation_only": True,
    }
    summary: dict[str, object] = {
        "headline": (
            "日週線形成中"
            if provisional
            else "等待資料確認" if contract.overall_status.value != "ready" else "五週期分析已更新"
        ),
        "direction": kam_decision.direction,
        "confidence": str(confidence.overall_confidence_score),
        "risk": risk.overall_risk_level.value,
        "next_step": kam_decision.primary_next_action,
        "action": "HOLD",
        "decision_status": "BLOCKED",
        "message": (
            "日線與週線仍在形成，僅顯示觀察結果。"
            if provisional
            else "資料尚未完整，維持觀察。"
            if contract.overall_status.value != "ready"
            else "KAM 九狀態映射已完成；決策維持唯讀觀察。"
        ),
    }
    kam_payload = kam_decision.safe_payload()
    kam_payload.update({
        "mapping_version": KAM_STATE_MAPPING_VERSION,
        "states": {item.timeframe: item.safe_payload() for item in mapped_states},
    })
    return VerifiedFiveTimeframeAnalysisPreview(
        evaluated_at=evaluated_at,
        overall_status=("provisional_current_periods" if provisional else contract.overall_status.value),
        timeframe_analysis=analysis,
        decision_diagnostics=diagnostics,
        three_second_summary=summary,
        kam_rule_decision=kam_payload,
        blockers=tuple(blockers),
    )


__all__ = [
    "VerifiedFiveTimeframeAnalysisPreview",
    "build_verified_five_timeframe_analysis_preview",
]
