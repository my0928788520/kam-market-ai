"""Paper-only day/night session close analysis and LINE report."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta
from hashlib import sha256
from typing import Any
from urllib.parse import quote
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

from .line_pending_order import LinePendingOrderAlert

TAIPEI = ZoneInfo("Asia/Taipei")
REFERENCE_SYMBOLS = {
    "標普期貨": "ES=F",
    "那指期貨": "NQ=F",
    "道指期貨": "YM=F",
    "美元台幣": "TWD=X",
}


@dataclass(frozen=True, slots=True)
class ReferenceReading:
    label: str
    symbol: str
    price: float | None
    change_percent: float | None
    observed_at: datetime | None
    status: str


@dataclass(frozen=True, slots=True)
class ExternalMarketContext:
    readings: tuple[ReferenceReading, ...]
    source: str = "YAHOO_PUBLIC_DELAYED_REFERENCE"

    def reading(self, label: str) -> ReferenceReading | None:
        return next((item for item in self.readings if item.label == label), None)


class PublicDelayedReferenceSource:
    """Fetch delayed public reference quotes; failure remains explicit and non-trading."""

    def __init__(
        self,
        *,
        opener: Callable[..., Any] = urlopen,
        timeout_seconds: float = 8,
    ) -> None:
        self.opener = opener
        self.timeout_seconds = timeout_seconds

    def load(self) -> ExternalMarketContext:
        return ExternalMarketContext(
            tuple(self._load_one(label, symbol) for label, symbol in REFERENCE_SYMBOLS.items())
        )

    def _load_one(self, label: str, symbol: str) -> ReferenceReading:
        endpoint = (
            "https://query1.finance.yahoo.com/v8/finance/chart/"
            f"{quote(symbol, safe='')}?interval=5m&range=1d"
        )
        request = Request(endpoint, headers={"User-Agent": "KAM-paper-research/0.1"})
        try:
            with self.opener(request, timeout=self.timeout_seconds) as response:
                payload = json.loads(response.read().decode("utf-8"))
            result = payload["chart"]["result"][0]
            meta = result["meta"]
            price_value = meta.get("regularMarketPrice")
            previous_value = meta.get("chartPreviousClose")
            timestamp_value = meta.get("regularMarketTime")
            price = float(price_value) if price_value is not None else None
            previous = float(previous_value) if previous_value is not None else None
            change = (
                ((price - previous) / previous) * 100
                if price is not None and previous not in {None, 0}
                else None
            )
            observed_at = (
                datetime.fromtimestamp(int(timestamp_value), UTC)
                if timestamp_value is not None
                else None
            )
            return ReferenceReading(label, symbol, price, change, observed_at, "delayed")
        except (KeyError, IndexError, OSError, TypeError, ValueError, json.JSONDecodeError):
            return ReferenceReading(label, symbol, None, None, None, "unavailable")


def _frame(payload: Mapping[str, object], key: str) -> Mapping[str, object]:
    preview = payload.get("analysis_preview")
    preview = preview if isinstance(preview, Mapping) else {}
    frames = preview.get("timeframes")
    frames = frames if isinstance(frames, Mapping) else {}
    frame = frames.get(key)
    return frame if isinstance(frame, Mapping) else {}


def _number(value: object) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def due_session_close(now: datetime) -> str | None:
    """Return one report slot during the first 30 minutes after each close."""
    if now.tzinfo is None:
        raise ValueError("session report clock must be timezone-aware")
    local = now.astimezone(TAIPEI)
    clock = local.time().replace(tzinfo=None)
    if local.weekday() < 5 and time(13, 45) <= clock < time(14, 15):
        return "regular"
    # Monday night through Friday night close on Tuesday through Saturday.
    if 1 <= local.weekday() <= 5 and time(5, 0) <= clock < time(5, 30):
        return "afterhours"
    return None


def desired_live_session(now: datetime) -> str:
    """Return the session that a continuously running service should follow."""
    if now.tzinfo is None:
        raise ValueError("automatic session clock must be timezone-aware")
    local = now.astimezone(TAIPEI)
    clock = local.time().replace(tzinfo=None)
    # Keep the day feed through its close-report window; change to night at open.
    if local.weekday() < 5 and time(8, 45) <= clock < time(15, 0):
        return "regular"
    return "afterhours"


def build_session_close_alert(
    payload: Mapping[str, object],
    context: ExternalMarketContext,
    *,
    session: str,
    observed_at: datetime,
    calibration: Mapping[str, object] | None = None,
) -> LinePendingOrderAlert:
    if session not in {"regular", "afterhours"} or observed_at.tzinfo is None:
        raise ValueError("invalid session close report")
    if payload.get("market_data_only") is not True or payload.get("live_order_allowed") is not False:
        raise ValueError("session report requires read-only market data")

    day = _frame(payload, "1d")
    sixty = _frame(payload, "60m")
    fifteen = _frame(payload, "15m")
    score = 50.0
    evidence = 0

    m60_bias = str(sixty.get("market_bias", "insufficient"))
    if m60_bias == "bullish":
        score += 18
        evidence += 1
    elif m60_bias == "bearish":
        score -= 18
        evidence += 1

    m15_position = str(fifteen.get("price_vs_ma20", "insufficient"))
    m15_direction = str(fifteen.get("ma20_direction", "insufficient"))
    if (m15_position, m15_direction) == ("above", "rising"):
        score += 12
        evidence += 1
    elif (m15_position, m15_direction) == ("below", "falling"):
        score -= 12
        evidence += 1

    daily_position = str(day.get("price_vs_ma60", "insufficient"))
    if daily_position == "above":
        score += 8
        evidence += 1
    elif daily_position == "below":
        score -= 8
        evidence += 1

    us_changes: list[float] = []
    if session == "afterhours":
        for label in ("標普期貨", "那指期貨", "道指期貨"):
            reading = context.reading(label)
            if reading is not None and reading.change_percent is not None:
                us_changes.append(reading.change_percent)
        if us_changes:
            score += max(-15, min(15, (sum(us_changes) / len(us_changes)) * 8))
            evidence += 1

    fx = context.reading("美元台幣")
    if fx is not None and fx.change_percent is not None:
        # Rising USD/TWD means a weaker TWD and is treated as a modest bearish input.
        score -= max(-5, min(5, fx.change_percent * 10))
        evidence += 1

    volume_ratio = _number(fifteen.get("volume_ratio_20"))
    volatility_ratio = _number(fifteen.get("volatility_ratio_20"))
    score = max(5.0, min(95.0, score))
    if evidence < 3:
        # Keep an incomplete report close to neutral rather than invent confidence.
        score = 50 + ((score - 50) * 0.5)
    if volume_ratio is not None:
        confirmation = max(0.5, min(1.15, volume_ratio))
        score = 50 + ((score - 50) * confirmation)
    score = max(5.0, min(95.0, score))
    bullish = round(score)
    bearish = 100 - bullish
    confidence = "資料不足" if evidence < 3 else "一般" if evidence < 5 else "較完整"
    calibration = calibration if isinstance(calibration, Mapping) else {}
    current_confirmation = calibration.get("current_confirmation")
    current_confirmation = (
        current_confirmation if isinstance(current_confirmation, Mapping) else {}
    )
    line_state = str(current_confirmation.get("line_confirmation", "partial"))
    line_label = "線型同向確認" if line_state == "confirmed" else "線型部分確認"
    volume_state = str(current_confirmation.get("volume_confirmation", "資料不足"))
    historical = current_confirmation.get("historical_group")
    historical = historical if isinstance(historical, Mapping) else {}
    historical_rate = historical.get("calibrated_success_rate")
    historical_sample = int(historical.get("sample_size", 0) or 0)
    historical_text = (
        "樣本不足"
        if historical_rate is None
        else f"{historical_rate}%（{historical_sample}筆・"
        f"{'樣本不足' if historical_sample < 30 else '初步可信' if historical_sample < 100 else '可信度較高'}）"
    )

    def change_text(label: str) -> str:
        reading = context.reading(label)
        if reading is None or reading.change_percent is None:
            return f"{label}：資料不足"
        return f"{label}：{reading.change_percent:+.2f}%（延遲參考）"

    local = observed_at.astimezone(TAIPEI)
    session_label = "日盤" if session == "regular" else "夜盤"
    identity = sha256(
        f"session-close:{session}:{local.date().isoformat()}".encode()
    ).hexdigest()
    text = "\n".join(
        (
            f"KAM {session_label}收盤分析",
            f"多方 {bullish}%｜空方 {bearish}%",
            f"60分：{m60_bias}｜15分：{m15_position}/{m15_direction}",
            f"成交量：{volume_ratio:.2f}倍20期均量" if volume_ratio is not None else "成交量：資料不足",
            f"獨立波動：{volatility_ratio:.2f}倍20期均幅" if volatility_ratio is not None else "獨立波動：資料不足",
            f"線型確認：{line_label}｜{volume_state}",
            f"歷史校準：{historical_text}",
            change_text("標普期貨"),
            change_text("那指期貨"),
            change_text("道指期貨"),
            change_text("美元台幣"),
            f"資料完整度：{confidence}",
            "說明：當盤占比為線型量價規則估計；歷史校準率另列",
            "模式：唯讀行情＋Paper Trading｜禁止真實下單",
        )
    )
    return LinePendingOrderAlert(identity, text, observed_at + timedelta(minutes=30))


__all__ = [
    "ExternalMarketContext",
    "PublicDelayedReferenceSource",
    "ReferenceReading",
    "build_session_close_alert",
    "desired_live_session",
    "due_session_close",
]
