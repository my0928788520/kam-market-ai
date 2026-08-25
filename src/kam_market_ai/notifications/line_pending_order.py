"""Deduplicated LINE alert for human review of a paper-only KAM proposal."""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta
from decimal import Decimal
from hashlib import sha256
from os import replace
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

LINE_PUSH_URL = "https://api.line.me/v2/bot/message/push"
LINE_DELIVERY_STATE_SCHEMA = "kam-line-paper-delivery-v1"
PAPER_SAMPLE_MILESTONES = frozenset({10, 20, 30})
TAIPEI = ZoneInfo("Asia/Taipei")
PAPER_QUOTE_STALE_SECONDS = 60
REFRESH_FAULT_STATE_SCHEMA = "kam-line-refresh-fault-v1"


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
        malformed_patterns = (
            "\ufffd",
            "ï¿½",
            "DateTimeOffset::",
        )
        unresolved_variable = re.search(r"(?m)(?:^|[：:：\s])\$\{?[A-Za-z_]\w*\}?", self.text)
        question_mark_identifier = re.search(r"(?m)^\?[A-Za-z_{(]", self.text)
        if (
            any(pattern in self.text for pattern in malformed_patterns)
            or unresolved_variable
            or question_mark_identifier
        ):
            raise ValueError("LINE_ALERT_TEXT_ENCODING_OR_TEMPLATE_INVALID")
        if self.live_order_allowed:
            raise ValueError("LINE alerts cannot enable live orders")


@dataclass(slots=True)
class PersistentRefreshFaultMonitor:
    state_path: str | Path
    failure_threshold: int = 3
    active_fault_id: str | None = field(default=None, init=False)
    last_success_at: datetime | None = field(default=None, init=False)

    def __post_init__(self) -> None:
        self.state_path = Path(self.state_path)
        if self.failure_threshold < 1:
            raise ValueError("refresh failure threshold must be positive")
        if not self.state_path.exists():
            return
        payload = json.loads(self.state_path.read_text(encoding="utf-8"))
        state_hash = payload.pop("state_hash", None) if isinstance(payload, dict) else None
        expected = sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        if (
            not isinstance(payload, dict)
            or payload.get("schema") != REFRESH_FAULT_STATE_SCHEMA
            or payload.get("live_order_allowed") is not False
            or state_hash != expected
        ):
            raise ValueError("invalid refresh fault state")
        fault_id = payload.get("active_fault_id")
        if fault_id is not None and (not isinstance(fault_id, str) or len(fault_id) != 64):
            raise ValueError("invalid refresh fault identity")
        last_success = payload.get("last_success_at")
        self.active_fault_id = fault_id
        self.last_success_at = (
            datetime.fromisoformat(str(last_success).replace("Z", "+00:00"))
            if last_success
            else None
        )

    def observe_failure(
        self,
        *,
        consecutive_failures: int,
        observed_at: datetime,
    ) -> LinePendingOrderAlert | None:
        if observed_at.tzinfo is None or consecutive_failures < self.failure_threshold:
            return None
        if self.active_fault_id is None:
            origin = self.last_success_at.isoformat() if self.last_success_at else "startup"
            self.active_fault_id = sha256(f"refresh-fault:{origin}".encode("utf-8")).hexdigest()
            self._save()
        last_success = (
            self.last_success_at.isoformat() if self.last_success_at else "尚無成功紀錄"
        )
        text = "\n".join(
            (
                "KAM Paper Trading 資料刷新失敗警告",
                f"連續失敗：{consecutive_failures} 次",
                f"最後成功時間：{last_success}",
                "狀態：等待下一輪自動重試",
                "安全：僅監控 Paper Trading，不會送出真實委託",
            )
        )
        return LinePendingOrderAlert(
            self.active_fault_id,
            text,
            observed_at + timedelta(minutes=5),
        )

    def observe_success(self, *, observed_at: datetime) -> LinePendingOrderAlert | None:
        if observed_at.tzinfo is None:
            raise ValueError("refresh success clock must be timezone-aware")
        previous_success = self.last_success_at
        self.last_success_at = observed_at
        self._save()
        if self.active_fault_id is None:
            return None
        recovery_id = sha256(f"{self.active_fault_id}:recovered".encode("utf-8")).hexdigest()
        text = "\n".join(
            (
                "KAM Paper Trading 資料連線已恢復",
                "中斷前最後成功時間："
                f"{previous_success.isoformat() if previous_success else '尚無紀錄'}",
                f"恢復時間：{observed_at.isoformat()}",
                "狀態：資料刷新已恢復正常",
                "安全：僅監控 Paper Trading，不會送出真實委託",
            )
        )
        return LinePendingOrderAlert(recovery_id, text, observed_at + timedelta(minutes=5))

    def acknowledge_recovery(self) -> None:
        self.active_fault_id = None
        self._save()

    def _save(self) -> None:
        payload: dict[str, object] = {
            "schema": REFRESH_FAULT_STATE_SCHEMA,
            "active_fault_id": self.active_fault_id,
            "last_success_at": self.last_success_at.isoformat() if self.last_success_at else None,
            "live_order_allowed": False,
        }
        payload["state_hash"] = sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.state_path.with_suffix(self.state_path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
            encoding="utf-8",
        )
        replace(temporary, self.state_path)


def build_pending_order_alert(
    payload: Mapping[str, object],
    *,
    take_profit_extension_points: Decimal = Decimal(20),
) -> LinePendingOrderAlert | None:
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
    try:
        quantity = Decimal(str(event.get("quantity")))
        entry_price = Decimal(str(event.get("entry_price")))
        stop_loss_price = Decimal(str(event.get("stop_loss_price")))
        take_profit_price = Decimal(str(event.get("take_profit_price")))
    except (ArithmeticError, TypeError, ValueError):
        return None
    direction = str(payload.get("direction", "")).upper()
    if (
        quantity != Decimal(1)
        or direction not in {"LONG", "SHORT"}
        or not take_profit_extension_points.is_finite()
        or take_profit_extension_points <= 0
    ):
        return None
    observed = datetime.fromisoformat(str(event["observed_at"]).replace("Z", "+00:00"))
    expires = observed + timedelta(minutes=15)
    side = "做多" if direction == "LONG" else "做空"
    extension_price = (
        take_profit_price + take_profit_extension_points
        if direction == "LONG"
        else take_profit_price - take_profit_extension_points
    )
    if not (
        stop_loss_price < entry_price < take_profit_price < extension_price
        if direction == "LONG"
        else extension_price < take_profit_price < entry_price < stop_loss_price
    ):
        return None
    text = "\n".join(
        (
            "KAM 模擬交易提案",
            f"方向：{side}",
            f"商品：{event['instrument']}",
            "口數：固定 1 口微台",
            f"建議進場：{event['entry_price']}",
            f"停損：{event['stop_loss_price']}",
            f"第一停利：{event['take_profit_price']}",
            f"延伸停利：{extension_price}",
            "出場條件：停損／第一停利／15分20MA條件失效",
            f"有效期限：{expires.isoformat()}",
            "狀態：等待本人確認",
            "模式：Paper Trading｜不會送出真實委託",
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
        "m15_ma20_rule_exit": "15分20MA條件失效平倉",
    }
    if event_type not in labels:
        return None
    proposal_hash = event.get("proposal_hash")
    fill_hash = event.get("fill_hash")
    if not isinstance(proposal_hash, str) or len(proposal_hash) != 64 or not fill_hash:
        return None
    observed = datetime.fromisoformat(str(event["observed_at"]))
    identity = sha256(f"{proposal_hash}:{event_type}:{fill_hash}".encode()).hexdigest()
    locked_side = str(event.get("entry_side", "")).lower()
    if locked_side not in {"buy", "sell"}:
        entry_price = Decimal(str(event.get("entry_price")))
        current_price = Decimal(str(event.get("current_price")))
        realized_pnl = Decimal(str(event.get("realized_pnl")))
        price_change = current_price - entry_price
        locked_side = (
            "buy"
            if price_change != 0 and realized_pnl * price_change > 0
            else "sell"
            if price_change != 0 and realized_pnl * price_change < 0
            else "buy"
            if Decimal(str(event.get("stop_loss_price"))) < entry_price
            else "sell"
        )
    side = "偏多" if locked_side == "buy" else "偏空"
    trigger_line = (
        f"實際停損觸發價：{event['stop_trigger_price']}"
        if event_type == "stop_loss_exit" and event.get("stop_trigger_price") is not None
        else None
    )
    lines = [
        f"KAM 模擬{labels[event_type]}",
        f"原方向：{side}",
        f"商品：{event['instrument']}",
        f"口數：{event['quantity']} 口",
        f"進場價：{event['entry_price']}",
        f"平倉價：{event['current_price']}",
        f"出場原因：{labels[event_type]}",
        f"已實現損益：{event['realized_pnl']}",
    ]
    if trigger_line is not None:
        lines.append(trigger_line)
    lines.extend(
        (
            f"平倉時間：{observed.isoformat()}",
            "狀態：模擬部位已平倉，舊提醒已停止",
            "安全：本通知不會送出真實委託",
        )
    )
    text = "\n".join(lines)
    return LinePendingOrderAlert(identity, text, observed + timedelta(minutes=5))


def build_paper_sample_milestone_alert(
    payload: Mapping[str, object],
    *,
    observed_at: datetime,
) -> LinePendingOrderAlert | None:
    """Build a deduplicated 10/20/30 closed-trade progress alert only."""
    if observed_at.tzinfo is None or payload.get("live_order_allowed") is not False:
        return None
    sample_size = payload.get("sample_size")
    if not isinstance(sample_size, int) or isinstance(sample_size, bool):
        return None
    if sample_size not in PAPER_SAMPLE_MILESTONES:
        return None
    minimum = payload.get("minimum_sample_size")
    if minimum != 30:
        return None
    identity = sha256(
        f"paper-performance-sample:{sample_size}:{minimum}".encode("utf-8")
    ).hexdigest()
    status = "已達可評估門檻" if sample_size >= minimum else f"距離門檻還差 {minimum - sample_size} 筆"
    text = "\n".join(
        (
            "KAM Paper Trading 樣本進度",
            f"已完成平倉：{sample_size} / {minimum} 筆",
            f"勝率：{payload.get('win_rate') or '資料不足'}%",
            f"期望值：{payload.get('expectancy') or '資料不足'}",
            f"獲利因子：{payload.get('profit_factor') or '資料不足'}",
            f"最大回撤：{payload.get('maximum_drawdown') or '資料不足'}",
            f"狀態：{status}",
            "安全：僅統計模擬交易，不會送出真實委託",
        )
    )
    return LinePendingOrderAlert(identity, text, observed_at + timedelta(minutes=5))


def _tmf_session_is_open(observed_at: datetime) -> bool:
    local = observed_at.astimezone(TAIPEI)
    current = local.timetz().replace(tzinfo=None)
    if local.weekday() == 5:
        return current < time(5)
    if local.weekday() == 6:
        return False
    overnight_open = local.weekday() > 0 and current < time(5)
    return time(8, 45) <= current <= time(13, 45) or current >= time(15) or overnight_open


def build_paper_health_alert(
    payload: Mapping[str, object],
    *,
    observed_at: datetime,
    quote_observed_at: datetime | None,
    journal_verified: bool,
) -> LinePendingOrderAlert | None:
    """Build one daily health summary or one fail-closed warning per Taiwan date."""
    if observed_at.tzinfo is None or payload.get("live_order_allowed") is not False:
        return None
    local_date = observed_at.astimezone(TAIPEI).date().isoformat()
    if not journal_verified:
        alert_kind = "journal-integrity"
        title = "KAM Paper Trading 日誌完整性警告"
        detail = "日誌驗證未通過，本輪模擬處理已停止"
    else:
        quote_age = (
            max(0, int((observed_at - quote_observed_at).total_seconds()))
            if quote_observed_at is not None and quote_observed_at.tzinfo is not None
            else None
        )
        if _tmf_session_is_open(observed_at) and (
            quote_age is None or quote_age > PAPER_QUOTE_STALE_SECONDS
        ):
            alert_kind = "quote-stale"
            title = "KAM Paper Trading 報價中斷警告"
            detail = (
                "交易時段內尚未取得報價"
                if quote_age is None
                else f"最新報價已延遲 {quote_age} 秒"
            )
        else:
            alert_kind = "daily-health"
            title = "KAM Paper Trading 每日健康摘要"
            detail = "系統、報價與模擬日誌檢查正常"
    identity = sha256(f"paper-health:{alert_kind}:{local_date}".encode("utf-8")).hexdigest()
    summary = payload.get("performance_summary")
    sample_size = summary.get("sample_size", 0) if isinstance(summary, Mapping) else 0
    quote_text = quote_observed_at.isoformat() if quote_observed_at is not None else "尚未取得"
    text = "\n".join(
        (
            title,
            f"日期：{local_date}",
            f"狀態：{detail}",
            f"最新報價時間：{quote_text}",
            f"今日累計平倉樣本：{sample_size} 筆",
            f"目前模擬部位：{payload.get('open_positions', 0)} 口",
            f"日誌驗證：{'正常' if journal_verified else '失敗'}",
            "安全：僅監控 Paper Trading，不會送出真實委託",
        )
    )
    return LinePendingOrderAlert(identity, text, observed_at + timedelta(minutes=5))


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
                "Content-Type": "application/json; charset=utf-8",
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
