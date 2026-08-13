"""Map normalized five-timeframe analysis into canonical KAM states."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from kam_market_ai.paper_trading.kam_rule_adapter import (
    KamReadOnlyDecision,
    KamTimeframeState,
    evaluate_kam_read_only_states,
)

KAM_STATE_MAPPING_VERSION = "five-timeframe-kam-state-v1.0"
_TIMEFRAMES = ("1w", "1d", "60m", "15m", "5m")
_BULLISH = frozenset({"bullish", "supportive"})
_BEARISH = frozenset({"bearish"})
_DEGRADED = frozenset({
    "stale", "insufficient", "ambiguous", "invalid", "unavailable",
    "calculation_error", "unknown", "conflicting",
})


@dataclass(frozen=True, slots=True)
class MappedKamTimeframeState:
    timeframe: str
    code: str
    directional_axis: str
    lifecycle_axis: str
    evidence: tuple[str, ...]

    def safe_payload(self) -> dict[str, object]:
        return {
            "code": self.code,
            "directional_axis": self.directional_axis,
            "lifecycle_axis": self.lifecycle_axis,
            "evidence": list(self.evidence),
        }


def map_analysis_frame_to_kam_state(
    timeframe: str,
    frame: Mapping[str, object],
) -> MappedKamTimeframeState:
    """Map A/N/B direction and U/F/D lifecycle without guessing unknown data."""
    if timeframe not in _TIMEFRAMES or not isinstance(frame, Mapping):
        raise ValueError("supported timeframe analysis is required")
    required = ("status", "position", "trend", "structure", "timing")
    if any(not isinstance(frame.get(name), str) for name in required):
        raise ValueError("normalized timeframe analysis fields are required")

    directional = tuple(str(frame[name]) for name in ("position", "trend", "structure"))
    bullish = sum(item in _BULLISH for item in directional)
    bearish = sum(item in _BEARISH for item in directional)
    degraded = any(item in _DEGRADED for item in directional)
    if not degraded and bullish > 0 and bearish == 0:
        direction = "A"
    elif not degraded and bearish > 0 and bullish == 0:
        direction = "B"
    else:
        direction = "N"

    status, timing = str(frame["status"]), str(frame["timing"])
    if status in {"stale", "invalid", "unavailable", "calculation_error", "ambiguous"} or timing in _DEGRADED:
        lifecycle = "D"
    elif status == "ready" and timing == "confirmed":
        lifecycle = "U"
    else:
        lifecycle = "F"
    return MappedKamTimeframeState(
        timeframe,
        direction + lifecycle,
        direction,
        lifecycle,
        directional + (timing, status),
    )


def evaluate_five_timeframe_kam_rules(
    analysis: Mapping[str, Mapping[str, object]],
) -> tuple[tuple[MappedKamTimeframeState, ...], KamReadOnlyDecision]:
    if not isinstance(analysis, Mapping) or any(item not in analysis for item in _TIMEFRAMES):
        raise ValueError("all five normalized timeframe analyses are required")
    mapped = tuple(map_analysis_frame_to_kam_state(item, analysis[item]) for item in _TIMEFRAMES)
    states = tuple(KamTimeframeState(item.code) for item in mapped)
    decision = evaluate_kam_read_only_states(*states)
    return mapped, decision


__all__ = [
    "KAM_STATE_MAPPING_VERSION",
    "MappedKamTimeframeState",
    "evaluate_five_timeframe_kam_rules",
    "map_analysis_frame_to_kam_state",
]
