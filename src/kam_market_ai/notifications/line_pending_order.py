"""Deduplicated LINE alert for human review of a paper-only KAM proposal."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any
from urllib.request import Request, urlopen

LINE_PUSH_URL = "https://api.line.me/v2/bot/message/push"


@dataclass(frozen=True, slots=True)
class LinePendingOrderAlert:
    proposal_hash: str
    text: str
    expires_at: datetime
    live_order_allowed: bool = False

    def __post_init__(self) -> None:
        if len(self.proposal_hash) != 64 or not self.text or self.expires_at.tzinfo is None:
            raise ValueError("invalid pending-order alert")
        if self.live_order_allowed:
            raise ValueError("LINE alerts cannot enable live orders")


def build_pending_order_alert(payload: Mapping[str, object]) -> LinePendingOrderAlert | None:
    """Build only from a completed paper entry; never include account data."""
    if payload.get("action") != "entry_filled" or payload.get("live_order_allowed") is not False:
        return None
    proposal_hash = payload.get("proposal_hash")
    event = payload.get("performance_event")
    boundary = payload.get("execution_boundary")
    if not isinstance(proposal_hash, str) or len(proposal_hash) != 64:
        return None
    if not isinstance(event, Mapping) or not isinstance(boundary, Mapping):
        return None
    if boundary.get("broker_submission_available") is not False:
        return None
    observed = datetime.fromisoformat(str(event["observed_at"]).replace("Z", "+00:00"))
    expires = observed + timedelta(minutes=15)
    side = "偏多" if str(payload.get("direction", "")).upper() == "LONG" else "偏空"
    text = "\n".join(
        (
            "KAM 待確認委託",
            f"方向：{side}",
            f"商品：{event['instrument']}",
            f"建議口數：{event['quantity']} 口",
            f"參考委託價：{event['entry_price']}",
            f"停損：{event['stop_loss_price']}",
            f"停利：{event['take_profit_price']}",
            f"有效期限：{expires.isoformat()}",
            "狀態：等待本人確認",
            "安全：本通知不會送出真實委託",
        )
    )
    return LinePendingOrderAlert(proposal_hash, text, expires)


@dataclass(slots=True, repr=False)
class LinePushNotifier:
    channel_access_token: str
    recipient_user_id: str
    timeout_seconds: float = 5
    opener: Callable[..., Any] = urlopen
    _sent_stages: set[tuple[str, int]] = field(default_factory=set, init=False, repr=False)

    def __post_init__(self) -> None:
        if not self.channel_access_token.strip() or not self.recipient_user_id.strip():
            raise ValueError("LINE alert configuration is incomplete")
        if self.timeout_seconds <= 0:
            raise ValueError("LINE alert timeout must be positive")

    def send_once(self, alert: LinePendingOrderAlert) -> bool:
        if not isinstance(alert, LinePendingOrderAlert):
            raise TypeError("LinePendingOrderAlert is required")
        if (alert.proposal_hash, 0) in self._sent_stages:
            return False
        return self._send(alert, alert.text, stage=0)

    def send_due(self, alert: LinePendingOrderAlert, now: datetime) -> bool:
        """Send immediate, three-minute, and expiry warnings without a backlog burst."""
        if now.tzinfo is None:
            raise ValueError("LINE alert clock must be timezone-aware")
        created_at = alert.expires_at - timedelta(minutes=15)
        if now >= alert.expires_at:
            return False
        elapsed = now - created_at
        stage = 2 if elapsed >= timedelta(minutes=14) else 1 if elapsed >= timedelta(minutes=3) else 0
        key = (alert.proposal_hash, stage)
        if key in self._sent_stages:
            return False
        prefix = {0: "", 1: "KAM 再次提醒\n", 2: "KAM 委託建議即將失效\n"}[stage]
        sent = self._send(alert, prefix + alert.text, stage=stage)
        if sent:
            self._sent_stages.update((alert.proposal_hash, item) for item in range(stage + 1))
        return sent

    def _send(self, alert: LinePendingOrderAlert, text: str, *, stage: int) -> bool:
        body = json.dumps(
            {"to": self.recipient_user_id, "messages": [{"type": "text", "text": text}]},
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        request = Request(
            LINE_PUSH_URL,
            data=body,
            headers={
                "Authorization": f"Bearer {self.channel_access_token}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with self.opener(request, timeout=self.timeout_seconds) as response:
            status = int(getattr(response, "status", 0))
            if status < 200 or status >= 300:
                raise RuntimeError("LINE_PUSH_REJECTED")
        self._sent_stages.add((alert.proposal_hash, stage))
        return True
