"""Read-only analysis preview for verified five-timeframe candles.

All five verified candle slices are evaluated with centralized provisional
parameters.  This boundary never turns provisional analysis into a trading
decision.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta

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
    RelationToTrendline,
    TrendEngineConfig,
    TrendlineType,
    TrendState,
    evaluate_all_trendlines,
)
from kam_market_ai.decision.decision_confidence import (
    DecisionConfidenceConfig,
    evaluate_decision_confidence,
)
from kam_market_ai.decision.decision_contract import (
    DecisionInputConfig,
    build_decision_input_contract,
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
from kam_market_ai.paper_trading.five_timeframe_paper_direction import (
    FiveTimeframePaperDirection,
    decide_five_timeframe_paper_direction,
)

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

_REFERENCE_WINDOW_BARS = 20
_REFERENCE_MINIMUM_BARS = 5
_FORMING_CAPABLE_TIMEFRAMES = {
    FiveTimeframe.M5,
    FiveTimeframe.M15,
    FiveTimeframe.M60,
}


def _five_timeframe_timing_config() -> TimingEngineConfig:
    """Keep every frame usable until its existing hard stale threshold.

    The generic provisional timing defaults mark a closed daily bar as delayed
    before the next regular session opens and a closed weekly bar as delayed
    during the following week.  The KAM mapper treats delayed as degraded, so
    those defaults make a verified five-timeframe ``AU`` state unreachable.
    This profile preserves the original hard stale limits while reserving the
    delayed band for the final minute/hour/day before each limit.
    """
    config = TimingEngineConfig.provisional()
    return replace(
        config,
        delayed_after_by_timeframe={
            PositionTimeframe.M5: timedelta(minutes=9),
            PositionTimeframe.M15: timedelta(minutes=29),
            PositionTimeframe.M60: timedelta(minutes=119),
            PositionTimeframe.D1: timedelta(hours=47),
            PositionTimeframe.W1: timedelta(days=13),
        },
    )


def _ma20_display_metrics(candles: tuple[Candle, ...]) -> dict[str, object]:
    """Expose only bounded display metrics; raw candle history stays outside snapshots."""
    closes = tuple(float(item.close) for item in candles)
    latest = closes[-1]
    if len(closes) < 20:
        return {
            "last_price": latest,
            "ma20": None,
            "price_vs_ma20": "insufficient",
            "ma20_direction": "insufficient",
        }
    ma20 = sum(closes[-20:]) / 20
    if latest > ma20:
        position = "above"
    elif latest < ma20:
        position = "below"
    else:
        position = "equal"
    direction = "insufficient"
    if len(closes) >= 21:
        previous = sum(closes[-21:-1]) / 20
        direction = "rising" if ma20 > previous else "falling" if ma20 < previous else "flat"
    return {
        "last_price": latest,
        "ma20": ma20,
        "price_vs_ma20": position,
        "ma20_direction": direction,
    }


def _m60_ma20_support_metrics(candles: tuple[Candle, ...]) -> dict[str, object]:
    """Classify support from closed 60-minute candles only.

    The live intraday series keeps a final forming candle.  It is deliberately
    excluded so a temporary intrabar dip cannot flip the control bias.
    """
    closed = candles[:-1]
    if len(closed) < 20:
        return {
            "ma20_support": "insufficient",
            "market_bias": "insufficient",
            "support_close": None,
            "support_low": None,
        }
    ma20 = sum(float(item.close) for item in closed[-20:]) / 20
    latest = closed[-1]
    close = float(latest.close)
    low = float(latest.low)
    if close < ma20:
        support = "broken"
        bias = "bearish"
    elif low <= ma20:
        support = "retest_held"
        bias = "bullish"
    else:
        support = "held"
        bias = "bullish"
    return {
        "ma20_support": support,
        "market_bias": bias,
        "support_close": close,
        "support_low": low,
    }


def _daily_ma60_display_metrics(candles: tuple[Candle, ...]) -> dict[str, object]:
    """Expose the closed daily MA60 relation used only as a direction filter."""
    closes = tuple(float(item.close) for item in candles)
    if len(closes) < 60:
        return {
            "ma60": None,
            "price_vs_ma60": "insufficient",
            "ma60_direction": "insufficient",
        }
    ma60 = sum(closes[-60:]) / 60
    latest = closes[-1]
    relation = "above" if latest > ma60 else "below" if latest < ma60 else "equal"
    direction = "insufficient"
    if len(closes) >= 61:
        previous = sum(closes[-61:-1]) / 60
        direction = "rising" if ma60 > previous else "falling" if ma60 < previous else "flat"
    return {
        "ma60": ma60,
        "price_vs_ma60": relation,
        "ma60_direction": direction,
    }


def _daily_descending_trendline_metrics(
    candles: tuple[Candle, ...],
) -> dict[str, object]:
    """Project a daily resistance line from two confirmed wave highs.

    Only completed daily bars are supplied at this boundary.  A pivot needs a
    completed bar on both sides.  Candidate lower-high pairs are considered
    newest-first and any pair already closed through is discarded, preventing
    an obsolete major high from projecting an unusable line into the present.
    """
    window = candles[-80:]
    insufficient = {
        "descending_trendline_state": "insufficient",
        "descending_trendline_relation": "insufficient",
        "descending_trendline_value": None,
        "descending_trendline_anchor_high_1": None,
        "descending_trendline_anchor_high_2": None,
        "descending_trendline_anchor_1_end": None,
        "descending_trendline_anchor_2_end": None,
        "descending_trendline_selection": "none",
        "descending_trendline_discarded_broken_pairs": 0,
        "bullish_weakening": None,
    }
    if len(window) < 5:
        return insufficient
    pivots = [
        index
        for index in range(1, len(window) - 1)
        if float(window[index].high) >= float(window[index - 1].high)
        and float(window[index].high) > float(window[index + 1].high)
    ]
    if len(pivots) < 2:
        return insufficient
    anchors: tuple[int, int] | None = None
    discarded_broken_pairs = 0
    for right_position in range(len(pivots) - 1, 0, -1):
        right = pivots[right_position]
        for left in reversed(pivots[:right_position]):
            first_high = float(window[left].high)
            second_high = float(window[right].high)
            if second_high >= first_high:
                continue
            slope = (second_high - first_high) / (right - left)

            if any(
                float(window[index].close) > first_high + slope * (index - left)
                for index in range(right + 1, len(window))
            ):
                discarded_broken_pairs += 1
                continue
            anchors = (left, right)
            break
        if anchors is not None:
            break
    if anchors is None:
        return {
            **insufficient,
            "descending_trendline_discarded_broken_pairs": discarded_broken_pairs,
        }
    left, right = anchors
    first_high = float(window[left].high)
    second_high = float(window[right].high)
    slope = (second_high - first_high) / (right - left)

    def line_at(index: int) -> float:
        return first_high + slope * (index - left)

    projected = line_at(len(window) - 1)
    latest = window[-1]
    close = float(latest.close)
    high = float(latest.high)
    if high >= projected and close <= projected:
        state = "rejected_below"
        relation = "rejection"
        weakening = True
    else:
        state = "active_below"
        relation = "below"
        # Being somewhere below a descending line is context, not a fresh
        # weakening confirmation.  Require the completed daily candle to
        # actually test the projected line and close back below it.
        weakening = False
    return {
        "descending_trendline_state": state,
        "descending_trendline_relation": relation,
        "descending_trendline_value": projected,
        "descending_trendline_anchor_high_1": first_high,
        "descending_trendline_anchor_high_2": second_high,
        "descending_trendline_anchor_1_end": window[left].end.isoformat(),
        "descending_trendline_anchor_2_end": window[right].end.isoformat(),
        "descending_trendline_selection": "recent_valid_lower_highs",
        "descending_trendline_discarded_broken_pairs": discarded_broken_pairs,
        "bullish_weakening": weakening,
    }


def _m15_trend_warning_codes(result: object) -> tuple[str, ...]:
    """Translate existing trend-engine states into observation-only weakening warnings."""
    warnings: list[str] = []
    trend_state = getattr(result, "trend_state", None)
    line_type = getattr(result, "active_trendline_type", None)
    relation = getattr(result, "relation_to_trendline", None)
    if (
        trend_state is TrendState.ASCENDING_BROKEN
        or (
            line_type is TrendlineType.ASCENDING
            and relation is RelationToTrendline.BREAKDOWN_DOWN
        )
    ):
        warnings.append("M15_ASCENDING_TRENDLINE_BROKEN_WEAKENING")
    if (
        line_type is TrendlineType.DESCENDING
        and (
            trend_state is TrendState.DESCENDING_RESISTED
            or relation in {RelationToTrendline.TOUCHING, RelationToTrendline.REJECTION}
        )
    ):
        warnings.append("M15_DESCENDING_TRENDLINE_RESISTANCE_WEAKENING")
    return tuple(warnings)


def _range_reference_metrics(
    candles: tuple[Candle, ...],
    *,
    exclude_latest: bool,
) -> dict[str, object]:
    """Expose bounded 20-bar range references without retaining candle history.

    Intraday feeds may include a still-forming final bar, so the latest 5/15/60
    minute candle is excluded.  Verified day/week history contains only closed
    bars and can use its latest candle.  Five bars are required before a range
    is presented as a reference.
    """
    reference = candles[:-1] if exclude_latest else candles
    window = reference[-_REFERENCE_WINDOW_BARS:]
    enough = len(window) >= _REFERENCE_MINIMUM_BARS
    return {
        "range_resistance": max(float(item.high) for item in window) if enough else None,
        "range_support": min(float(item.low) for item in window) if enough else None,
        "range_window_bars": len(window),
        "range_excludes_latest": exclude_latest,
    }


@dataclass(frozen=True, slots=True)
class VerifiedFiveTimeframeAnalysisPreview:
    evaluated_at: datetime
    overall_status: str
    timeframe_analysis: dict[str, dict[str, object]]
    decision_diagnostics: dict[str, object]
    three_second_summary: dict[str, object]
    kam_rule_decision: dict[str, object]
    paper_direction: FiveTimeframePaperDirection
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
        forming_source = series[FiveTimeframe.M60]
        first, last = forming_source[0], forming_source[-1]
        forming = Candle(
            instrument=first.instrument,
            start=first.start,
            end=last.end,
            open=first.open,
            high=max(item.high for item in forming_source),
            low=min(item.low for item in forming_source),
            close=last.close,
            volume=sum(item.volume for item in forming_source),
        )
        series[FiveTimeframe.DAY] = (forming,)
        series[FiveTimeframe.WEEK] = (forming,)
    candles = {engine: series[source] for source, engine in _ENGINE_TIMEFRAMES.items()}
    current_prices = {engine: series[-1].close for engine, series in candles.items()}
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
        _five_timeframe_timing_config(),
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

    trend_warning_codes = _m15_trend_warning_codes(trend[PositionTimeframe.M15])
    analysis: dict[str, dict[str, object]] = {}
    for source_timeframe, engine in _ENGINE_TIMEFRAMES.items():
        frame = contract.timeframes[engine]
        analysis[source_timeframe.value] = {
            "status": frame.input_status.value,
            "usable": frame.usable,
            "position": frame.position.normalized_state.value,
            "trend": frame.trend.normalized_state.value,
            "structure": frame.structure.normalized_state.value,
            "timing": frame.timing.normalized_state.value,
            "error_codes": list(frame.error_codes),
            **_ma20_display_metrics(series[source_timeframe]),
            **(
                _m60_ma20_support_metrics(series[source_timeframe])
                if source_timeframe is FiveTimeframe.M60
                else {}
            ),
            **(
                _daily_ma60_display_metrics(series[source_timeframe])
                if source_timeframe is FiveTimeframe.DAY
                else {}
            ),
            **(
                _daily_descending_trendline_metrics(series[source_timeframe])
                if source_timeframe is FiveTimeframe.DAY
                else {}
            ),
            **(
                {"trend_warning_codes": list(trend_warning_codes)}
                if source_timeframe is FiveTimeframe.M15
                else {}
            ),
            **_range_reference_metrics(
                series[source_timeframe],
                exclude_latest=source_timeframe in _FORMING_CAPABLE_TIMEFRAMES,
            ),
        }

    blockers: list[str] = []
    if provisional:
        blockers.append("CURRENT_DAY_WEEK_BARS_ARE_PROVISIONAL")
    if contract.overall_status.value != "ready":
        blockers.append("ANALYSIS_INPUT_NOT_READY")
    mapped_states, kam_decision = evaluate_five_timeframe_kam_rules(analysis)
    paper_direction = decide_five_timeframe_paper_direction(
        mapped_states,
        daily_ma60_position=str(analysis["1d"].get("price_vs_ma60", "insufficient")),
        trend_warning_codes=trend_warning_codes,
        m15_ma20_position=str(analysis["15m"].get("price_vs_ma20", "insufficient")),
        m15_ma20_direction=str(analysis["15m"].get("ma20_direction", "insufficient")),
        m60_ma20_support=str(analysis["60m"].get("ma20_support", "insufficient")),
        m60_market_bias=str(analysis["60m"].get("market_bias", "insufficient")),
        daily_descending_trendline_state=str(
            analysis["1d"].get("descending_trendline_state", "insufficient")
        ),
        daily_bullish_weakening=analysis["1d"].get("bullish_weakening"),
    )
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
        "trend_warning_codes": list(trend_warning_codes),
        "daily_ma60_position": analysis["1d"].get("price_vs_ma60", "insufficient"),
        "daily_descending_trendline_state": analysis["1d"].get(
            "descending_trendline_state", "insufficient"
        ),
        "daily_descending_trendline_relation": analysis["1d"].get(
            "descending_trendline_relation", "insufficient"
        ),
        "daily_bullish_weakening": analysis["1d"].get("bullish_weakening"),
        "m15_ma20_position": analysis["15m"].get("price_vs_ma20", "insufficient"),
        "m15_ma20_direction": analysis["15m"].get("ma20_direction", "insufficient"),
        "m60_ma20_support": analysis["60m"].get("ma20_support", "insufficient"),
        "m60_market_bias": analysis["60m"].get("market_bias", "insufficient"),
        "max_contracts": 1,
        "scale_in_allowed": False,
        "observation_only": True,
    }
    summary: dict[str, object] = {
        "headline": (
            "日週線形成中"
            if provisional
            else "等待資料確認"
            if contract.overall_status.value != "ready"
            else "五週期分析已更新"
        ),
        "direction": kam_decision.direction,
        "confidence": str(confidence.overall_confidence_score),
        "risk": risk.overall_risk_level.value,
        "next_step": kam_decision.primary_next_action,
        "action": "HOLD",
        "decision_status": "BLOCKED",
        "message": (
            "15分上升趨勢線跌破，注意可能轉弱。"
            if "M15_ASCENDING_TRENDLINE_BROKEN_WEAKENING" in trend_warning_codes
            else "15分波浪反彈碰到下降趨勢線，注意可能轉弱。"
            if "M15_DESCENDING_TRENDLINE_RESISTANCE_WEAKENING" in trend_warning_codes
            else "日線與週線仍在形成，僅顯示觀察結果。"
            if provisional
            else "資料尚未完整，維持觀察。"
            if contract.overall_status.value != "ready"
            else "KAM 九狀態映射已完成；決策維持唯讀觀察。"
        ),
    }
    kam_payload = kam_decision.safe_payload()
    kam_payload.update(
        {
            "mapping_version": KAM_STATE_MAPPING_VERSION,
            "states": {item.timeframe: item.safe_payload() for item in mapped_states},
            "paper_test_direction": paper_direction.safe_payload(),
        }
    )
    return VerifiedFiveTimeframeAnalysisPreview(
        evaluated_at=evaluated_at,
        overall_status=(
            "provisional_current_periods" if provisional else contract.overall_status.value
        ),
        timeframe_analysis=analysis,
        decision_diagnostics=diagnostics,
        three_second_summary=summary,
        kam_rule_decision=kam_payload,
        paper_direction=paper_direction,
        blockers=tuple(blockers),
    )


__all__ = [
    "VerifiedFiveTimeframeAnalysisPreview",
    "build_verified_five_timeframe_analysis_preview",
]
