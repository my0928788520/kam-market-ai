"""Fail-closed boundary between verified live candles and KAM decisions."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class LiveFiveTimeframeDecisionReadiness:
    data_status: str
    decision_status: str
    action: str
    blockers: tuple[str, ...]
    loaded_timeframes: tuple[str, ...]
    missing_timeframes: tuple[str, ...]
    market_data_only: bool = True
    live_order_allowed: bool = False

    def safe_payload(self) -> dict[str, object]:
        return {
            "success": False,
            "data_status": self.data_status,
            "decision_status": self.decision_status,
            "action": self.action,
            "blockers": list(self.blockers),
            "loaded_timeframes": list(self.loaded_timeframes),
            "missing_timeframes": list(self.missing_timeframes),
            "market_data_only": self.market_data_only,
            "live_order_allowed": self.live_order_allowed,
        }


def evaluate_live_five_timeframe_readiness(
    payload: Mapping[str, object],
) -> LiveFiveTimeframeDecisionReadiness:
    """Accept only safe verifier output and never infer unimplemented states."""
    if not isinstance(payload, Mapping):
        raise TypeError("verified five-timeframe payload is required")

    status = payload.get("status")
    loaded = payload.get("loaded_timeframes")
    missing = payload.get("missing_timeframes")

    if not isinstance(status, str):
        raise ValueError("verified five-timeframe status is required")
    if not isinstance(loaded, list) or not all(isinstance(item, str) for item in loaded):
        raise ValueError("loaded_timeframes must be a string list")
    if not isinstance(missing, list) or not all(isinstance(item, str) for item in missing):
        raise ValueError("missing_timeframes must be a string list")
    if payload.get("market_data_only") is not True:
        raise ValueError("live decision gate accepts market-data-only payloads")
    if payload.get("trading_enabled") is not False:
        raise ValueError("live decision gate rejects trading-enabled payloads")

    blockers: list[str] = []
    if status != "READY_VERIFIED_FIVE_TIMEFRAMES" or missing:
        blockers.append("FIVE_TIMEFRAME_DATA_INCOMPLETE")
    else:
        blockers.append("TIMEFRAME_STATE_CLASSIFICATION_REQUIRED")

    return LiveFiveTimeframeDecisionReadiness(
        data_status=status,
        decision_status="BLOCKED",
        action="HOLD",
        blockers=tuple(blockers),
        loaded_timeframes=tuple(loaded),
        missing_timeframes=tuple(missing),
    )


__all__ = [
    "LiveFiveTimeframeDecisionReadiness",
    "evaluate_live_five_timeframe_readiness",
]
