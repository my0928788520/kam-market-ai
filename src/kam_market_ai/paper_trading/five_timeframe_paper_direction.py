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
    daily_ma60_position: str | None = None
    trend_warning_codes: tuple[str, ...] = ()

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
            "daily_ma60_position": self.daily_ma60_position,
            "trend_warning_codes": list(self.trend_warning_codes),
        }


def decide_five_timeframe_paper_direction(
    states: tuple[MappedKamTimeframeState, ...],
    *,
    daily_ma60_position: str | None = None,
    trend_warning_codes: tuple[str, ...] = (),
) -> FiveTimeframePaperDirection:
    """Select long, short, or hold without constructing or sending an order.

    Daily MA60 is a direction filter.  Fifteen-minute trendline warnings block
    fresh long entries but never create an opposite order by themselves.
    """
    if len(states) != 5 or not all(
        isinstance(item, MappedKamTimeframeState) for item in states
    ):
        raise TypeError("five mapped KAM timeframe states are required")
    if daily_ma60_position not in {None, "above", "below", "equal", "insufficient"}:
        raise ValueError("daily_ma60_position must be a normalized MA60 relation")
    if not isinstance(trend_warning_codes, tuple) or not all(
        isinstance(item, str) for item in trend_warning_codes
    ):
        raise TypeError("trend_warning_codes must be a tuple of strings")

    codes = tuple(item.code for item in states)
    weakening = {
        "M15_ASCENDING_TRENDLINE_BROKEN_WEAKENING",
        "M15_DESCENDING_TRENDLINE_RESISTANCE_WEAKENING",
    }.intersection(trend_warning_codes)

    if codes == ("AU",) * 5:
        if daily_ma60_position not in {None, "above"}:
            return FiveTimeframePaperDirection(
                "HOLD", "NO_PAPER_ORDER", "DAILY_MA60_NOT_BULLISH",
                codes, False, daily_ma60_position=daily_ma60_position,
                trend_warning_codes=trend_warning_codes,
            )
        if weakening:
            return FiveTimeframePaperDirection(
                "HOLD", "NO_PAPER_ORDER", "M15_TREND_WEAKENING_WARNING",
                codes, False, daily_ma60_position=daily_ma60_position,
                trend_warning_codes=trend_warning_codes,
            )
        return FiveTimeframePaperDirection(
            "LONG", "PAPER_BUY", "FIVE_TIMEFRAME_BULLISH_CONFIRMED", codes, True,
            daily_ma60_position=daily_ma60_position,
            trend_warning_codes=trend_warning_codes,
        )

    if codes == ("BU",) * 5:
        if daily_ma60_position not in {None, "below"}:
            return FiveTimeframePaperDirection(
                "HOLD", "NO_PAPER_ORDER", "DAILY_MA60_NOT_BEARISH",
                codes, False, daily_ma60_position=daily_ma60_position,
                trend_warning_codes=trend_warning_codes,
            )
        return FiveTimeframePaperDirection(
            "SHORT", "PAPER_SELL", "FIVE_TIMEFRAME_BEARISH_CONFIRMED", codes, True,
            daily_ma60_position=daily_ma60_position,
            trend_warning_codes=trend_warning_codes,
        )

    return FiveTimeframePaperDirection(
        "HOLD", "NO_PAPER_ORDER", "FIVE_TIMEFRAME_NOT_FULLY_ALIGNED", codes, False,
        daily_ma60_position=daily_ma60_position,
        trend_warning_codes=trend_warning_codes,
    )


__all__ = ["FiveTimeframePaperDirection", "decide_five_timeframe_paper_direction"]
