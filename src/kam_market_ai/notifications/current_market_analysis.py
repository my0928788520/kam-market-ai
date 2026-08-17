"""Stable five-minute market analysis for the read-only KAM dashboard."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from hashlib import sha256

from .line_pending_order import LinePendingOrderAlert


def _frame(payload: Mapping[str, object], key: str) -> Mapping[str, object]:
    preview = payload.get("analysis_preview")
    preview = preview if isinstance(preview, Mapping) else {}
    frames = preview.get("timeframes")
    frames = frames if isinstance(frames, Mapping) else {}
    value = frames.get(key)
    return value if isinstance(value, Mapping) else {}


def _decision(payload: Mapping[str, object]) -> Mapping[str, object]:
    preview = payload.get("analysis_preview")
    preview = preview if isinstance(preview, Mapping) else {}
    rule = preview.get("kam_rule_decision")
    rule = rule if isinstance(rule, Mapping) else {}
    direction = rule.get("paper_test_direction")
    return direction if isinstance(direction, Mapping) else {}


@dataclass(frozen=True, slots=True)
class CurrentMarketAnalysis:
    headline: str
    basis: str
    conflict: str
    waiting_for: str
    risk: str
    fingerprint: str
    bucket: str

    def safe_payload(self) -> dict[str, str]:
        return {
            "headline": self.headline,
            "basis": self.basis,
            "conflict": self.conflict,
            "waiting_for": self.waiting_for,
            "risk": self.risk,
            "fingerprint": self.fingerprint,
            "bucket": self.bucket,
        }


def build_current_market_analysis(
    payload: Mapping[str, object], *, observed_at: datetime
) -> CurrentMarketAnalysis:
    """Build deterministic prose without price-tick noise or trade authority."""
    if observed_at.tzinfo is None:
        raise ValueError("market analysis clock must be timezone-aware")
    bucket_time = observed_at.replace(
        minute=observed_at.minute - observed_at.minute % 5,
        second=0,
        microsecond=0,
    )
    bucket = bucket_time.isoformat()
    day = _frame(payload, "1d")
    sixty = _frame(payload, "60m")
    fifteen = _frame(payload, "15m")
    five = _frame(payload, "5m")
    decision = _decision(payload)
    status = str(payload.get("status", ""))
    stale = status != "READY_VERIFIED_FIVE_TIMEFRAMES" or any(
        str(frame.get("status", "")) in {"stale", "invalid", "unavailable", "insufficient"}
        for frame in (day, sixty, fifteen, five)
    )
    if stale:
        values = (
            "資料不足，暫停盤勢判讀",
            "五週期資料尚未全部通過新鮮度與完整性驗證",
            "目前無法可靠比較長短週期方向",
            "等待資料恢復並完成下一個五分鐘週期",
            "禁止依過期資料建立新的模擬委託",
        )
    else:
        day_above = str(day.get("price_vs_ma60", "")) == "above"
        m60_support = str(sixty.get("ma20_support", "")) == "held"
        m60_bias = str(sixty.get("market_bias", ""))
        m15_position = str(fifteen.get("price_vs_ma20", ""))
        m15_direction = str(fifteen.get("ma20_direction", ""))
        m5_position = str(five.get("price_vs_ma20", ""))
        bullish_base = day_above and m60_support and m60_bias == "bullish"
        bearish_base = (not day_above) and m60_bias == "bearish"
        short_bullish = m15_position == "above" and m15_direction == "rising" and m5_position == "above"
        short_bearish = m15_position == "below" and m15_direction == "falling" and m5_position == "below"
        if bullish_base and short_bullish:
            headline = "五週期偏多條件增強，等待模擬進場確認"
        elif bearish_base and short_bearish:
            headline = "五週期偏空條件增強，等待模擬進場確認"
        elif bullish_base:
            headline = "中期偏多、短線尚未同步，維持觀望"
        elif bearish_base:
            headline = "中期偏空、短線尚未同步，維持觀望"
        else:
            headline = "五週期方向尚未一致，維持觀望"
        basis_parts = [
            "日線在60MA上方" if day_above else "日線未站上60MA",
            "60分20MA支撐未破" if m60_support else "60分20MA支撐未確認",
            "60分偏多" if m60_bias == "bullish" else "60分偏空" if m60_bias == "bearish" else "60分方向待確認",
        ]
        conflict_parts = []
        if m15_position != ("above" if bullish_base else "below" if bearish_base else m15_position):
            conflict_parts.append("15分位置尚未配合中期方向")
        if bullish_base and not short_bullish:
            conflict_parts.append("5分與15分尚未同步轉強")
        elif bearish_base and not short_bearish:
            conflict_parts.append("5分與15分尚未同步轉弱")
        reason = str(decision.get("reason_code", ""))
        values = (
            headline,
            "、".join(basis_parts),
            "、".join(conflict_parts) or ("短週期已配合" if reason else "等待更多週期證據"),
            "等待15分與5分完成多方確認" if bullish_base else "等待15分與5分完成空方確認" if bearish_base else "等待長短週期重新一致",
            "60分有效跌破20MA則注意轉弱" if bullish_base else "60分重新站回20MA則取消偏空判斷" if bearish_base else "方向未一致前不建立新模擬部位",
        )
    canonical = json.dumps(values, ensure_ascii=False, separators=(",", ":"))
    return CurrentMarketAnalysis(*values, sha256(canonical.encode("utf-8")).hexdigest(), bucket)


def build_current_market_analysis_alert(
    analysis: CurrentMarketAnalysis, *, observed_at: datetime
) -> LinePendingOrderAlert:
    identity = sha256(
        f"current-market-analysis:{analysis.bucket}:{analysis.fingerprint}".encode()
    ).hexdigest()
    text = "\n".join(
        (
            "KAM 現況分析更新",
            f"盤勢：{analysis.headline}",
            f"理由：{analysis.basis}",
            f"矛盾：{analysis.conflict}",
            f"等待：{analysis.waiting_for}",
            f"風險：{analysis.risk}",
            f"更新時間：{analysis.bucket}",
            "模式：Paper Trading｜最多1口微台｜不會送出真實委託",
        )
    )
    return LinePendingOrderAlert(identity, text, observed_at + timedelta(minutes=5))


__all__ = [
    "CurrentMarketAnalysis",
    "build_current_market_analysis",
    "build_current_market_analysis_alert",
]
