"""Deduplicated LINE alert for human review of a paper-only KAM proposal."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from hashlib import sha256
from os import replace
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

LINE_PUSH_URL = "https://api.line.me/v2/bot/message/push"
LINE_DELIVERY_STATE_SCHEMA = "kam-line-paper-delivery-v1"


def _delivery_state_payload(sent_stages: set[tuple[str, int]]) -> dict[str, object]:
    entries = [
        {"alert_hash": alert_hash, "stage": stage}
        for alert_hash, stage in sorted(sent_stages)
    ]
    canonical = {
        "schema": LINE_DELIVERY_STATE_SCHEMA,
        "sent_stages": entries,
        "live_order_allowed": False,
    }
    canonical["state_hash"] = sha256(
        json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return canonical


def _load_delivery_state(path: Path) -> set[tuple[str, int]]:
    if not path.exists():
        return set()
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("schema") != LINE_DELIVERY_STATE_SCHEMA:
        raise ValueError("invalid LINE delivery state")
    state_hash = payload.pop("state_hash", None)
    expected = sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    if state_hash != expected or payload.get("live_order_allowed") is not False:
        raise ValueError("invalid LINE delivery state hash")
    entries = payload.get("sent_stages")
    if not isinstance(entries, list):
        raise ValueError("invalid LINE delivery entries")
    sent: set[tuple[str, int]] = set()
    for item in entries:
        if not isinstance(item, dict):
            raise ValueError("invalid LINE delivery entry")
        alert_hash = item.get("alert_hash")
        stage = item.get("stage")
        if not isinstance(alert_hash, str) or len(alert_hash) != 64 or stage not in {0, 1, 2}:
            raise ValueError("invalid LINE delivery identity")
        sent.add((alert_hash, stage))
    return sent


def _save_delivery_state(path: Path, sent_stages: set[tuple[str, int]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(
            _delivery_state_payload(sent_stages),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ),
        encoding="utf-8",
    )
    replace(temporary, path)


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


def build_paper_exit_alert(payload: Mapping[str, object]) -> LinePendingOrderAlert | None:
    """Build one close alert and cancel the meaning of any pending entry reminder."""
    if payload.get("action") != "exit_filled" or payload.get("live_order_allowed") is not False:
        return None
    event = payload.get("performance_event")
    boundary = payload.get("execution_boundary")
    if not isinstance(event, Mapping) or not isinstance(boundary, Mapping):
        return None
    if boundary.get("broker_submission_available") is not False:
        return None
    event_type = str(event.get("event_type", ""))
    labels = {
        "stop_loss_exit": "停損平倉",
        "take_profit_exit": "停利平倉",
    }
    if event_type not in labels:
        return None
    proposal_hash = event.get("proposal_hash")
    fill_hash = event.get("fill_hash")
    if not isinstance(proposal_hash, str) or len(proposal_hash) != 64 or not fill_hash:
        return None
    observed = datetime.fromisoformat(str(event["observed_at"]).replace("Z", "+00:00"))
    identity = sha256(f"{proposal_hash}:{event_type}:{fill_hash}".encode("utf-8")).hexdigest()
    side = (
        "偏多"
        if Decimal(str(event.get("stop_loss_price"))) < Decimal(str(event.get("entry_price")))
        else "偏空"
    )
    text = "\n".join(
        (
            f"KAM 模擬{labels[event_type]}",
            f"原方向：{side}",
            f"商品：{event['instrument']}",
            f"口數：{event['quantity']} 口",
            f"進場價：{event['entry_price']}",
            f"平倉價：{event['current_price']}",
            f"已實現損益：{event['realized_pnl']}",
            f"平倉時間：{observed.isoformat()}",
            "狀態：模擬部位已平倉，舊提醒已停止",
            "安全：本通知不會送出真實委託",
        )
    )
    return LinePendingOrderAlert(identity, text, observed + timedelta(minutes=5))


@dataclass(slots=True, repr=False)
class LinePushNotifier:
    channel_access_token: str
    recipient_user_id: str
    timeout_seconds: float = 5
    opener: Callable[..., Any] = urlopen
    state_path: str | Path | None = None
    _sent_stages: set[tuple[str, int]] = field(default_factory=set, init=False, repr=False)

    def __post_init__(self) -> None:
        if not self.channel_access_token.strip() or not self.recipient_user_id.strip():
            raise ValueError("LINE alert configuration is incomplete")
        if self.timeout_seconds <= 0:
            raise ValueError("LINE alert timeout must be positive")
        if self.state_path is not None:
            self.state_path = Path(self.state_path)
            self._sent_stages.update(_load_delivery_state(self.state_path))

    def send_once(self, alert: LinePendingOrderAlert) -> bool:
        if not isinstance(alert, LinePendingOrderAlert):
            raise TypeError("LinePendingOrderAlert is required")
        if (alert.proposal_hash, 0) in self._sent_stages:
            return False
        self._send(alert, alert.text)
        self._sent_stages.add((alert.proposal_hash, 0))
        self._persist()
        return True

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
        self._send(alert, prefix + alert.text)
        self._sent_stages.update((alert.proposal_hash, item) for item in range(stage + 1))
        self._persist()
        return True

    def _send(self, alert: LinePendingOrderAlert, text: str) -> None:
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

    def _persist(self) -> None:
        if isinstance(self.state_path, Path):
            _save_delivery_state(self.state_path, self._sent_stages)
