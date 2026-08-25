"""Read-only day/night Paper Trading calibration and signal confirmation."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import datetime, time
from decimal import Decimal
from math import sqrt
from typing import Any
from zoneinfo import ZoneInfo

from .session_direction_quality_gate import (
    completed_trade_audit,
    quality_metrics,
)

TAIPEI = ZoneInfo("Asia/Taipei")
EXIT_EVENT_TYPES = {
    "stop_loss_exit",
    "profit_lock_exit",
    "take_profit_exit",
    "m15_ma20_rule_exit",
}


def _value(event: object, name: str) -> object:
    if isinstance(event, Mapping):
        return event.get(name)
    return getattr(event, name, None)


def _event_type(event: object) -> str:
    value = _value(event, "event_type")
    return str(getattr(value, "value", value))


def _session(event: object) -> str:
    observed = _value(event, "observed_at")
    if isinstance(observed, str):
        observed = datetime.fromisoformat(observed)
    if not isinstance(observed, datetime) or observed.tzinfo is None:
        raise ValueError("paper event timestamp must be timezone-aware")
    local = observed.astimezone(TAIPEI)
    clock = local.time().replace(tzinfo=None)
    return "regular" if time(8, 45) <= clock < time(13, 45) else "afterhours"


def _direction(event: object) -> str:
    entry = Decimal(str(_value(event, "entry_price")))
    stop = Decimal(str(_value(event, "stop_loss_price")))
    return "LONG" if stop < entry else "SHORT"


def _wilson_interval(wins: int, sample: int) -> tuple[float, float] | None:
    if sample == 0:
        return None
    z = 1.96
    rate = wins / sample
    denominator = 1 + (z * z / sample)
    center = (rate + z * z / (2 * sample)) / denominator
    margin = (
        z
        * sqrt((rate * (1 - rate) / sample) + z * z / (4 * sample * sample))
        / denominator
    )
    return max(0, center - margin) * 100, min(1, center + margin) * 100


def _group_payload(outcomes: list[Decimal]) -> dict[str, object]:
    sample = len(outcomes)
    wins = sum(value > 0 for value in outcomes)
    losses = sum(value < 0 for value in outcomes)
    breakeven = sample - wins - losses
    gross_profit = sum((value for value in outcomes if value > 0), Decimal(0))
    gross_loss = abs(sum((value for value in outcomes if value < 0), Decimal(0)))
    interval = _wilson_interval(wins, sample)
    metrics = quality_metrics(outcomes)
    recovery_mode = (
        sample >= 2
        and int(metrics["consecutive_losses"]) >= 2
        and metrics["expectancy"] is not None
        and Decimal(str(metrics["expectancy"])) < 0
    )
    return {
        "sample_size": sample,
        "wins": wins,
        "losses": losses,
        "breakeven": breakeven,
        "win_rate": None if sample == 0 else round(wins / sample * 100, 2),
        # Beta(5, 5) shrinkage prevents tiny samples from looking certain.
        "calibrated_success_rate": (
            None if sample == 0 else round((wins + 5) / (sample + 10) * 100, 2)
        ),
        "confidence_interval_95": (
            None if interval is None else [round(interval[0], 2), round(interval[1], 2)]
        ),
        "profit_factor": (
            None if gross_loss == 0 else str((gross_profit / gross_loss).quantize(Decimal("0.01")))
        ),
        "net_pnl": str(sum(outcomes, Decimal(0))),
        "confidence": "insufficient" if sample < 30 else "preliminary" if sample < 100 else "established",
        "minimum_sample_size": 30,
        **metrics,
        "quality_gate_state": "recovery" if recovery_mode else "normal",
        "recommended_confirmation_candles": 3 if recovery_mode else 1,
        "early_candidate_allowed": not recovery_mode,
    }


def _frame(payload: Mapping[str, object], key: str) -> Mapping[str, object]:
    preview = payload.get("analysis_preview")
    preview = preview if isinstance(preview, Mapping) else {}
    frames = preview.get("timeframes")
    frames = frames if isinstance(frames, Mapping) else {}
    frame = frames.get(key)
    return frame if isinstance(frame, Mapping) else {}


def _number(value: object) -> float | None:
    try:
        return None if value is None else float(value)
    except (TypeError, ValueError):
        return None


def _current_confirmation(payload: Mapping[str, object]) -> dict[str, object]:
    day = _frame(payload, "1d")
    sixty = _frame(payload, "60m")
    fifteen = _frame(payload, "15m")
    score = 50.0
    line_evidence: list[str] = []
    conflicts: list[str] = []

    m60 = str(sixty.get("market_bias", "insufficient"))
    if m60 == "bullish":
        score += 18
        line_evidence.append("60分偏多")
    elif m60 == "bearish":
        score -= 18
        line_evidence.append("60分偏空")

    m15_position = str(fifteen.get("price_vs_ma20", "insufficient"))
    m15_direction = str(fifteen.get("ma20_direction", "insufficient"))
    if (m15_position, m15_direction) == ("above", "rising"):
        score += 16
        line_evidence.append("15分站上上彎20MA")
    elif (m15_position, m15_direction) == ("below", "falling"):
        score -= 16
        line_evidence.append("15分跌破下彎20MA")
    else:
        conflicts.append("15分線型尚未同向")

    trendline = str(day.get("descending_trendline_state", "insufficient"))
    if trendline == "broken_above":
        score += 10
        line_evidence.append("日線突破下降趨勢線")
    elif trendline in {"rejected_below", "active_below"}:
        score -= 10
        line_evidence.append("日線受下降趨勢線壓制")

    volume_ratio = _number(fifteen.get("volume_ratio_20"))
    raw_edge = score - 50
    if volume_ratio is None:
        volume_state = "資料不足"
        raw_edge *= 0.65
    elif volume_ratio >= 1.2:
        volume_state = "放量確認"
        raw_edge *= 1.15
    elif volume_ratio >= 0.8:
        volume_state = "量能一般"
    else:
        volume_state = "量縮・方向降權"
        raw_edge *= 0.65
    score = max(5.0, min(95.0, 50 + raw_edge))
    bullish = round(score)
    direction = "LONG" if bullish >= 55 else "SHORT" if bullish <= 45 else "HOLD"
    return {
        "direction": direction,
        "bullish_ratio": bullish,
        "bearish_ratio": 100 - bullish,
        "line_confirmation": "confirmed" if len(line_evidence) >= 2 and not conflicts else "partial",
        "line_evidence": line_evidence,
        "line_conflicts": conflicts,
        "volume_ratio_20": volume_ratio,
        "volume_confirmation": volume_state,
    }


def build_session_direction_calibration(
    events: Iterable[Any],
    payload: Mapping[str, object],
    *,
    session: str | None = None,
) -> dict[str, object]:
    """Calibrate four session/direction groups from completed paper trades."""
    if (
        payload.get("market_data_only") is not True
        or payload.get("live_order_allowed") is not False
    ):
        raise ValueError("session calibration requires read-only market data")
    if session is not None and session not in {"regular", "afterhours"}:
        raise ValueError("invalid calibration session")
    outcomes, anomalies = completed_trade_audit(events)

    groups = {
        key: {
            **_group_payload(values),
            "excluded_anomalous_trades": len(anomalies[key]),
            "statistics_integrity": (
                "anomalies_excluded" if anomalies[key] else "verified"
            ),
        }
        for key, values in outcomes.items()
    }
    current = _current_confirmation(payload)
    session = session or _session_clock_from_payload(payload)
    direction = current["direction"]
    selected = groups.get(f"{session}_{direction}") if direction in {"LONG", "SHORT"} else None
    current["session"] = session
    current["historical_group"] = selected
    return {
        "groups": groups,
        "current_confirmation": current,
        "excluded_anomalous_trades": sum(map(len, anomalies.values())),
        "dry_run": True,
        "live_order_allowed": False,
    }


def _session_clock_from_payload(payload: Mapping[str, object]) -> str:
    value = str(payload.get("session") or "").lower()
    if value in {"regular", "afterhours"}:
        return value
    return "afterhours" if payload.get("after_hours") is True else "regular"


__all__ = ["build_session_direction_calibration"]
