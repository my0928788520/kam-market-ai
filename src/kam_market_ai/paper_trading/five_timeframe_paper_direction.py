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
    daily_descending_trendline_state: str | None = None
    daily_bullish_weakening: bool | None = None
    trend_warning_codes: tuple[str, ...] = ()
    m15_ma20_position: str | None = None
    m15_ma20_direction: str | None = None
    m60_ma20_support: str | None = None
    m60_market_bias: str | None = None
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
            "daily_descending_trendline_state": self.daily_descending_trendline_state,
            "daily_bullish_weakening": self.daily_bullish_weakening,
            "trend_warning_codes": list(self.trend_warning_codes),
            "m15_ma20_position": self.m15_ma20_position,
            "m15_ma20_direction": self.m15_ma20_direction,
            "m60_ma20_support": self.m60_ma20_support,
            "m60_market_bias": self.m60_market_bias,
            "max_contracts": 1,
            "scale_in_allowed": False,
            "averaging_down_allowed": False,
        }


def decide_five_timeframe_paper_direction(
    states: tuple[MappedKamTimeframeState, ...],
    *,
    daily_ma60_position: str | None = None,
    daily_descending_trendline_state: str | None = None,
    daily_bullish_weakening: bool | None = None,
    trend_warning_codes: tuple[str, ...] = (),
    m15_ma20_position: str | None = None,
    m15_ma20_direction: str | None = None,
    m60_ma20_support: str | None = None,
    m60_market_bias: str | None = None,
) -> FiveTimeframePaperDirection:
    """Select a paper direction from M60 location and an M15 trigger.

    Closed M60 candles provide the primary directional location: held MA20
    support permits longs, while a confirmed break permits shorts.  Closed M15
    MA20 position and slope provide the actual entry trigger.  The remaining
    timeframes, daily MA60, and trendline warnings stay in the payload as
    context; they do not impose the former five-timeframe alignment veto.
    Quantity remains capped at one Micro Taiwan Index Futures contract with no
    scale-in or averaging down, and this function never enables live orders.
    """
    if len(states) != 5 or not all(
        isinstance(item, MappedKamTimeframeState) for item in states
    ):
        raise TypeError("five mapped KAM timeframe states are required")
    if daily_ma60_position not in {None, "above", "below", "equal", "insufficient"}:
        raise ValueError("daily_ma60_position must be a normalized MA60 relation")
    if daily_descending_trendline_state not in {
        None,
        "active_below",
        "rejected_below",
        "broken_above",
        "insufficient",
    }:
        raise ValueError("daily_descending_trendline_state must be normalized")
    if daily_bullish_weakening not in {None, True, False}:
        raise ValueError("daily_bullish_weakening must be a boolean or None")
    if m15_ma20_position not in {None, "above", "below", "equal", "insufficient"}:
        raise ValueError("m15_ma20_position must be a normalized MA20 relation")
    if m15_ma20_direction not in {None, "rising", "falling", "flat", "insufficient"}:
        raise ValueError("m15_ma20_direction must be a normalized MA20 direction")
    if m60_ma20_support not in {None, "held", "retest_held", "broken", "insufficient"}:
        raise ValueError("m60_ma20_support must be a normalized support state")
    if m60_market_bias not in {None, "bullish", "bearish", "neutral", "insufficient"}:
        raise ValueError("m60_market_bias must be a normalized market bias")
    if not isinstance(trend_warning_codes, tuple) or not all(
        isinstance(item, str) for item in trend_warning_codes
    ):
        raise TypeError("trend_warning_codes must be a tuple of strings")

    codes = tuple(item.code for item in states)
    payload = {
        "daily_ma60_position": daily_ma60_position,
        "daily_descending_trendline_state": daily_descending_trendline_state,
        "daily_bullish_weakening": daily_bullish_weakening,
        "trend_warning_codes": trend_warning_codes,
        "m15_ma20_position": m15_ma20_position,
        "m15_ma20_direction": m15_ma20_direction,
        "m60_ma20_support": m60_ma20_support,
        "m60_market_bias": m60_market_bias,
    }
    if m60_market_bias == "bullish" and m60_ma20_support in {"held", "retest_held"}:
        if m15_ma20_position == "above" and m15_ma20_direction == "rising":
            return FiveTimeframePaperDirection(
                "LONG", "PAPER_BUY", "M60_BULLISH_M15_LONG_TRIGGER", codes, True,
                **payload,
            )
        reason_code = "M15_MA20_LONG_TRIGGER_NOT_CONFIRMED"
    elif m60_market_bias == "bearish" and m60_ma20_support == "broken":
        if m15_ma20_position == "below" and m15_ma20_direction == "falling":
            reason = (
                "D1_DESCENDING_TRENDLINE_WEAKENING_M60_M15_SHORT_TRIGGER"
                if daily_bullish_weakening is True
                and daily_descending_trendline_state == "rejected_below"
                else "M60_BEARISH_M15_SHORT_TRIGGER"
            )
            return FiveTimeframePaperDirection(
                "SHORT", "PAPER_SELL", reason, codes, True,
                **payload,
            )
        reason_code = "M15_MA20_SHORT_TRIGGER_NOT_CONFIRMED"
    elif m60_market_bias in {None, "insufficient"} or m60_ma20_support in {
        None,
        "insufficient",
    }:
        reason_code = "M60_LOCATION_INSUFFICIENT"
    else:
        reason_code = "M60_LOCATION_NOT_DIRECTIONAL"

    return FiveTimeframePaperDirection(
        "HOLD", "NO_PAPER_ORDER", reason_code, codes, False, **payload,
    )


__all__ = ["FiveTimeframePaperDirection", "decide_five_timeframe_paper_direction"]
