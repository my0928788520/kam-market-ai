"""Fail-closed direction gate for isolated five-timeframe paper tests."""

from __future__ import annotations

from dataclasses import dataclass

from kam_market_ai.live_read_only.five_timeframe_kam_rule_bridge import (
    MappedKamTimeframeState,
)


@dataclass(frozen=True, slots=True)
class FiveTimeframePaperDirection:
    direction: str
    action: str
    reason_code: str
    timeframe_states: tuple[str, ...]
    eligible: bool
    dry_run: bool = True
    live_order_allowed: bool = False
    broker_connected: bool = False

    def safe_payload(self) -> dict[str, object]:
        return {
            "direction": self.direction,
            "action": self.action,
            "reason_code": self.reason_code,
            "timeframe_states": list(self.timeframe_states),
            "eligible": self.eligible,
            "dry_run": True,
            "live_order_allowed": False,
            "broker_connected": False,
        }


def decide_five_timeframe_paper_direction(
    states: tuple[MappedKamTimeframeState, ...],
) -> FiveTimeframePaperDirection:
    """Select long, short, or hold without constructing or sending an order."""
    if len(states) != 5 or not all(
        isinstance(item, MappedKamTimeframeState) for item in states
    ):
        raise TypeError("five mapped KAM timeframe states are required")
    codes = tuple(item.code for item in states)
    if codes == ("AU",) * 5:
        return FiveTimeframePaperDirection(
            "LONG", "PAPER_BUY", "FIVE_TIMEFRAME_BULLISH_CONFIRMED", codes, True
        )
    if codes == ("BU",) * 5:
        return FiveTimeframePaperDirection(
            "SHORT", "PAPER_SELL", "FIVE_TIMEFRAME_BEARISH_CONFIRMED", codes, True
        )
    return FiveTimeframePaperDirection(
        "HOLD", "NO_PAPER_ORDER", "FIVE_TIMEFRAME_NOT_FULLY_ALIGNED", codes, False
    )


__all__ = ["FiveTimeframePaperDirection", "decide_five_timeframe_paper_direction"]
