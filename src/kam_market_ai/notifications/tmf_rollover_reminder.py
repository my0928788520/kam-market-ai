"""Calendar-based TMF monthly rollover reminders for LINE notification only."""

from __future__ import annotations

from calendar import monthcalendar
from datetime import date, datetime, time, timedelta
from hashlib import sha256
from zoneinfo import ZoneInfo

from .line_pending_order import LinePendingOrderAlert

TAIPEI = ZoneInfo("Asia/Taipei")


def third_wednesday(year: int, month: int) -> datetime:
    wednesdays = [week[2] for week in monthcalendar(year, month) if week[2]]
    return datetime.combine(
        date(year, month, wednesdays[2]),
        time(13, 30),
        tzinfo=TAIPEI,
    )


def _next_month(year: int, month: int) -> tuple[int, int]:
    return (year + 1, 1) if month == 12 else (year, month + 1)


def next_tmf_rollover(now: datetime) -> datetime:
    if now.tzinfo is None:
        raise ValueError("rollover reminder clock must be timezone-aware")
    local_now = now.astimezone(TAIPEI)
    rollover = third_wednesday(local_now.year, local_now.month)
    if local_now > rollover:
        year, month = _next_month(local_now.year, local_now.month)
        rollover = third_wednesday(year, month)
    return rollover


def build_due_tmf_rollover_alert(
    now: datetime,
    *,
    symbol: str,
) -> LinePendingOrderAlert | None:
    """Return the latest due reminder stage; delivery state handles deduplication."""
    if not symbol or symbol != symbol.strip().upper():
        raise ValueError("canonical TMF symbol is required")
    rollover = next_tmf_rollover(now)
    local_now = now.astimezone(TAIPEI)
    days_until = (rollover.date() - local_now.date()).days
    if days_until == 0:
        stage = "到期日提醒"
        stage_key = "day-of"
    elif days_until == 1:
        stage = "前一日提醒"
        stage_key = "one-day"
    elif 2 <= days_until <= 7:
        stage = "提前提醒"
        stage_key = "advance"
    else:
        return None
    identity = sha256(
        f"TMF_ROLLOVER:{rollover.date().isoformat()}:{stage_key}".encode()
    ).hexdigest()
    text = "\n".join(
        (
            f"KAM TMF 月契約換倉｜{stage}",
            f"目前商品：{symbol}",
            f"本月第 3 個星期三：{rollover.date().isoformat()}",
            "到期月契約一般交易至 13:30，當日沒有盤後交易",
            "請確認新月契約與流動性，再由本人決定是否換倉",
            "如遇假日或不可抗力，請以期交所公告的實際最後交易日為準",
            "安全：本通知不會送出、修改或取消任何真實委託",
        )
    )
    return LinePendingOrderAlert(identity, text, rollover + timedelta(minutes=5))


__all__ = [
    "TAIPEI",
    "build_due_tmf_rollover_alert",
    "next_tmf_rollover",
    "third_wednesday",
]
