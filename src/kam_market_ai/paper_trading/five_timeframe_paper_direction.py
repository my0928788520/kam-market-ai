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
    m15_ma20_position: str | None = None
    m15_ma20_direction: str | None = None
    max_contracts: int = 1

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
            "m15_ma20_position": self.m15_ma20_position,
            "m15_ma20_direction": self.m15_ma20_direction,
            "max_contracts": 1,
            "scale_in_allowed": False,
            "averaging_down_allowed": False,
        }


def decide_five_timeframe_paper_direction(
    states: tuple[MappedKamTimeframeState, ...],
    *,
    daily_ma60_position: str | None = None,
    trend_warning_codes: tuple[str, ...] = (),
    m15_ma20_position: str | None = None,
    m15_ma20_direction: str | None = None,
) -> FiveTimeframePaperDirection:
    """Select long, short, or hold without constructing or sending an order.

    Daily MA60 is a direction filter.  Closed M15 MA20 position and slope are
    entry triggers.  Trendline warnings block fresh long entries but never
    create an opposite order by themselves.  Quantity is permanently capped at
    one Micro Taiwan Index Futures contract with no scale-in or averaging down.
    """
    if len(states) != 5 or not all(
        isinstance(item, MappedKamTimeframeState) for item in states
    ):
        raise TypeError("five mapped KAM timeframe states are required")
    if daily_ma60_position not in {None, "above", "below", "equal", "insufficient"}:
        raise ValueError("daily_ma60_position must be a normalized MA60 relation")
    if m15_ma20_position not in {None, "above", "below", "equal", "insufficient"}:
        raise ValueError("m15_ma20_position must be a normalized MA20 relation")
    if m15_ma20_direction not in {None, "rising", "falling", "flat", "insufficient"}:
        raise ValueError("m15_ma20_direction must be a normalized MA20 direction")
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
                m15_ma20_position=m15_ma20_position,
                m15_ma20_direction=m15_ma20_direction,
            )
        if m15_ma20_position not in {None, "above"} or m15_ma20_direction not in {None, "rising"}:
            return FiveTimeframePaperDirection(
                "HOLD", "NO_PAPER_ORDER", "M15_MA20_LONG_TRIGGER_NOT_CONFIRMED",
                codes, False, daily_ma60_position=daily_ma60_position,
                trend_warning_codes=trend_warning_codes,
                m15_ma20_position=m15_ma20_position,
                m15_ma20_direction=m15_ma20_direction,
            )
        if weakening:
            return FiveTimeframePaperDirection(
                "HOLD", "NO_PAPER_ORDER", "M15_TREND_WEAKENING_WARNING",
                codes, False, daily_ma60_position=daily_ma60_position,
                trend_warning_codes=trend_warning_codes,
                m15_ma20_position=m15_ma20_position,
                m15_ma20_direction=m15_ma20_direction,
            )
        return FiveTimeframePaperDirection(
            "LONG", "PAPER_BUY", "FIVE_TIMEFRAME_BULLISH_CONFIRMED", codes, True,
            daily_ma60_position=daily_ma60_position,
            trend_warning_codes=trend_warning_codes,
            m15_ma20_position=m15_ma20_position,
            m15_ma20_direction=m15_ma20_direction,
        )

    if codes == ("BU",) * 5:
        if daily_ma60_position not in {None, "below"}:
            return FiveTimeframePaperDirection(
                "HOLD", "NO_PAPER_ORDER", "DAILY_MA60_NOT_BEARISH",
                codes, False, daily_ma60_position=daily_ma60_position,
                trend_warning_codes=trend_warning_codes,
                m15_ma20_position=m15_ma20_position,
                m15_ma20_direction=m15_ma20_direction,
            )
        if m15_ma20_position not in {None, "below"} or m15_ma20_direction not in {None, "falling"}:
            return FiveTimeframePaperDirection(
                "HOLD", "NO_PAPER_ORDER", "M15_MA20_SHORT_TRIGGER_NOT_CONFIRMED",
                codes, False, daily_ma60_position=daily_ma60_position,
                trend_warning_codes=trend_warning_codes,
                m15_ma20_position=m15_ma20_position,
                m15_ma20_direction=m15_ma20_direction,
            )
        return FiveTimeframePaperDirection(
            "SHORT", "PAPER_SELL", "FIVE_TIMEFRAME_BEARISH_CONFIRMED", codes, True,
            daily_ma60_position=daily_ma60_position,
            trend_warning_codes=trend_warning_codes,
            m15_ma20_position=m15_ma20_position,
            m15_ma20_direction=m15_ma20_direction,
        )

    return FiveTimeframePaperDirection(
        "HOLD", "NO_PAPER_ORDER", "FIVE_TIMEFRAME_NOT_FULLY_ALIGNED", codes, False,
        daily_ma60_position=daily_ma60_position,
        trend_warning_codes=trend_warning_codes,
        m15_ma20_position=m15_ma20_position,
        m15_ma20_direction=m15_ma20_direction,
    )


__all__ = ["FiveTimeframePaperDirection", "decide_five_timeframe_paper_direction"]
