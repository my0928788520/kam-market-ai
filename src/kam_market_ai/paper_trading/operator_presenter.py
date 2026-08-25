"""HTML-safe, read-only presentation for local Paper Trading review."""
from __future__ import annotations

from dataclasses import dataclass
from html import escape
from typing import Any

from .matching_engine import PaperTradingMatchingResult
from .order_proposal import PaperOrderProposalResult


PAPER_TRADING_OPERATOR_PRESENTER_VERSION = "0.1"

_VALUE_LABELS = {
    "buy": "多單進場", "sell": "空單進場", "close": "平倉（平多／回補）", "hold": "觀望",
    "market": "市價", "limit": "限價", "confirmed": "已人工確認",
    "required": "等待人工確認", "not_applicable": "不適用", "rejected": "已拒絕",
    "expired": "已過期", "filled": "已完成", "partially_filled": "部分成交",
    "open": "等待中", "cancelled": "已取消", "blocked": "已阻擋",
    "pending": "等待中", "not_confirmed": "尚未人工確認", "not_available": "尚無結果",
    "acceptable": "可接受", "caution": "注意", "proposal_generated": "委託建議已產生",
    "proposal_confirmed": "委託建議已人工確認", "proposal_rejected": "委託建議已拒絕",
    "proposal_expired": "委託建議已過期", "order_filled": "模擬撮合已完成",
    "order_rejected": "模擬撮合已拒絕", "order_open": "模擬撮合等待中",
    "order_partially_filled": "模擬撮合部分成交", "order_cancelled": "模擬撮合已取消",
}


@dataclass(frozen=True, slots=True)
class PaperTradingOperatorView:
    title: str
    summary: str
    proposal: dict[str, str]
    matching: dict[str, str]
    ledger: dict[str, str]
    audit_events: tuple[dict[str, str], ...]
    emergency_stop: bool
    read_only: bool = True
    dry_run: bool = True
    live_order_allowed: bool = False
    broker_connected: bool = False
    demo: dict[str, object] | None = None

    def __post_init__(self) -> None:
        if not self.read_only or self.dry_run is not True or self.live_order_allowed is not False or self.broker_connected is not False:
            raise ValueError("Operator view must remain local read-only paper trading.")


def _text(value: Any) -> str:
    raw = "—" if value is None else str(value)
    return escape(_VALUE_LABELS.get(raw.lower(), raw), quote=True)


def build_operator_presenter(proposal_result: PaperOrderProposalResult, matching_result: PaperTradingMatchingResult | None = None, *, emergency_stop: bool = False) -> PaperTradingOperatorView:
    """Build a deterministic view only; this function has no side effects."""
    if not isinstance(proposal_result, PaperOrderProposalResult):
        raise TypeError("PaperOrderProposalResult is required.")
    proposal = proposal_result.proposal
    proposal_fields = {"status": _text(proposal_result.status.value), "reasons": _text(", ".join(proposal_result.reason_codes) or "—")}
    audit: list[dict[str, str]] = [{"type": _text(proposal_result.audit_event.event_type), "hash": _text(proposal_result.audit_event.proposal_hash)}]
    if proposal is not None:
        source = proposal.input
        proposal_fields.update({"instrument": _text(source.instrument), "action": _text(source.action.value), "quantity": _text(source.quantity), "reference_price": _text(source.reference_price), "limit_price": _text(source.limit_price), "stop_loss": _text(source.stop_loss_price), "take_profit": _text(source.take_profit_price), "confidence": _text(source.confidence), "risk": _text(source.risk.status.value), "expires_at": _text(source.expires_at), "proposal_hash": _text(proposal.proposal_hash)})
    matching = {"state": "尚未人工確認", "fills": "0", "reasons": "—"}
    ledger = {"cash": "—", "positions": "—", "ledger_hash": "—"}
    if matching_result is not None:
        matching = {"state": _text(matching_result.state.value), "fills": _text(len(matching_result.fills)), "reasons": _text(", ".join(matching_result.reason_codes) or "—")}
        ledger = {"cash": _text(matching_result.ledger.cash_balance), "positions": _text(len(matching_result.ledger.positions)), "ledger_hash": _text(matching_result.ledger.ledger_hash)}
        audit.append({"type": _text(matching_result.audit_event.event_type), "hash": _text(matching_result.audit_event.audit_hash)})
    summary = "緊急停止已啟動，拒絕所有新的模擬委託。" if emergency_stop else "僅供模擬交易檢視，必須經人工確認。"
    return PaperTradingOperatorView("KAM 期貨模擬交易操作台", summary, proposal_fields, matching, ledger, tuple(audit), emergency_stop)


def build_demo_operator_presenter(proposal_result: PaperOrderProposalResult, matching_result: PaperTradingMatchingResult, snapshot: object) -> PaperTradingOperatorView:
    """Add explicitly-labelled fixed DEMO data to an otherwise read-only view."""
    view = build_operator_presenter(proposal_result, matching_result)
    timeframes = tuple(getattr(snapshot, "timeframes"))
    demo = {"banner": "示範資料・非即時行情・僅供流程驗收", "data_freshness": "DEMO", "instrument": getattr(snapshot, "instrument"), "snapshot_time": getattr(snapshot, "snapshot_time"), "current_price": getattr(snapshot, "current_price"), "u_stage": getattr(snapshot, "u_stage"), "timeframes": timeframes, "downside_watch": getattr(snapshot, "downside_watch"), "upside_resistance": getattr(snapshot, "upside_resistance"), "direction": "偏多", "direction_reason": "週線與 60 分維持偏多，短線等待確認。", "bull_score": "62", "bear_score": "38", "trend_health": "整理", "position": "多單", "average_price": getattr(snapshot, "current_price"), "unrealized_pnl": "0", "commentary": "示範市場評論：資料固定，請勿作為真實行情判斷。", "next_step": "人工確認示範流程。"}
    return PaperTradingOperatorView(view.title, view.summary, view.proposal, view.matching, view.ledger, view.audit_events, view.emergency_stop, demo=demo)
