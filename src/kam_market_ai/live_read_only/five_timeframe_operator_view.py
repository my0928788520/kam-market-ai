"""Project a safe five-timeframe snapshot into the canonical KAM operator UI."""

from __future__ import annotations

from collections.abc import Mapping

from kam_market_ai.paper_trading.operator_presenter import PaperTradingOperatorView

_FRAME_LABELS = (("1w", "週線"), ("1d", "日線"), ("60m", "60 分"), ("15m", "15 分"), ("5m", "5 分"))
_RISK_LABELS = {
    "low": "低風險",
    "moderate": "中等風險",
    "high": "高風險",
    "critical": "極高風險",
    "unknown": "資料不足",
    "stale": "資料逾時",
    "fresh": "資料正常",
}
_DIRECTION_LABELS = {
    "HOLD": "觀望",
    "NEUTRAL": "觀望",
    "LONG": "偏多",
    "SHORT": "偏空",
    "BUY": "買進",
    "SELL": "賣出",
}
_MARGIN_STATUS_LABELS = {
    "no_position": "目前無部位",
    "safe": "保證金安全",
    "healthy": "保證金充足",
    "maintenance_warning": "低於維持保證金",
    "margin_call": "保證金追繳警示",
}
_PAPER_ACTION_LABELS = {
    "DISARMED": "尚未武裝",
    "WAITING_FOR_KAM": "等待 KAM 條件",
    "hold": "觀望／未建立模擬委託",
    "pending_manual_confirmation": "等待模擬交易授權",
    "entry_filled": "模擬進場已成交",
    "position_marked": "模擬持倉追蹤中",
    "exit_filled": "模擬出場已成交",
    "rejected": "風控阻擋",
    "duplicate_ignored": "重複訊號已忽略",
}
_PAPER_REASON_LABELS = {
    "KAM_CONDITION_NOT_MET": "KAM 條件尚未成立",
    "KAM_BUY_CONDITION_NOT_MET": "KAM 買進條件尚未成立",
    "KAM_ENTRY_CONDITION_NOT_MET": "KAM 多空條件尚未成立",
    "PAPER_TRADING_NOT_ARMED": "自動模擬尚未啟用",
    "MANUAL_CONFIRMATION_REQUIRED": "本次工作階段尚未授權",
    "INSUFFICIENT_INITIAL_MARGIN": "模擬保證金不足",
    "REENTRY_COOLDOWN_ACTIVE": "出場冷卻期尚未結束",
    "MAX_DAILY_LOSS_EXCEEDED": "單日虧損已達停止交易上限",
    "MAX_DAILY_ENTRIES_EXCEEDED": "單日進場次數已達上限",
    "QUOTE_STALE": "行情資料過期",
}
_LINE_ALERT_STATUS_LABELS = {
    "DISABLED": "未啟用",
    "ARMED_WAITING_FOR_PAPER_PROPOSAL": "已啟用・等待模擬提案",
    "SENT": "已傳送",
    "EXIT_SENT": "平倉通知已傳送",
    "WAITING_OR_DUPLICATE": "等待下一階段",
    "RETRY_PENDING": "傳送失敗・等待重試",
}


def build_five_timeframe_operator_view(
    payload: Mapping[str, object],
    paper_runtime: Mapping[str, object] | None = None,
) -> PaperTradingOperatorView:
    """Build the established read-only operator view without inventing trade data."""
    if not isinstance(payload, Mapping):
        raise TypeError("five-timeframe payload is required")
    if payload.get("market_data_only") is not True or payload.get("trading_enabled") is not False:
        raise ValueError("operator projection requires safe market-data-only input")

    preview = payload.get("analysis_preview")
    preview = preview if isinstance(preview, Mapping) else {}
    summary = preview.get("three_second_summary")
    summary = summary if isinstance(summary, Mapping) else {}
    decision = preview.get("kam_rule_decision")
    decision = decision if isinstance(decision, Mapping) else {}
    states = decision.get("states")
    states = states if isinstance(states, Mapping) else {}
    analysis = preview.get("timeframes")
    analysis = analysis if isinstance(analysis, Mapping) else {}
    five_minute = analysis.get("5m")
    five_minute = five_minute if isinstance(five_minute, Mapping) else {}

    raw_direction = str(decision.get("direction", summary.get("direction", "觀望")))
    direction = _DIRECTION_LABELS.get(raw_direction.upper(), raw_direction)
    state_codes = []
    timeframes = []
    for key, label in _FRAME_LABELS:
        state = states.get(key)
        state = state if isinstance(state, Mapping) else {}
        code = str(state.get("code", "ND"))
        state_codes.append(code)
        timeframes.append((label, code))
    bull = sum(code.startswith("A") for code in state_codes)
    bear = sum(code.startswith("B") for code in state_codes)
    bull_score = bull * 20
    bear_score = bear * 20
    unconfirmed_score = max(0, 100 - bull_score - bear_score)

    status = str(payload.get("status", "資料不足"))
    next_step = str(decision.get("primary_next_action", summary.get("next_step", "等待資料完整")))
    paper = paper_runtime if isinstance(paper_runtime, Mapping) else {}
    paper_armed = paper.get("armed") is True
    paper_action = str(paper.get("action", "WAITING_FOR_KAM" if paper_armed else "DISARMED"))
    paper_action_label = _PAPER_ACTION_LABELS.get(paper_action, paper_action)
    paper_reasons = paper.get("reason_codes", ())
    if not isinstance(paper_reasons, (list, tuple)):
        paper_reasons = ()
    open_positions = int(paper.get("open_positions", 0) or 0)
    performance = paper.get("performance_event")
    performance = performance if isinstance(performance, Mapping) else {}
    margin_state = paper.get("margin_state")
    margin_state = margin_state if isinstance(margin_state, Mapping) else {}
    execution_boundary = paper.get("execution_boundary")
    execution_boundary = execution_boundary if isinstance(execution_boundary, Mapping) else {}
    real_order_requires_human = execution_boundary.get("real_order_requires_human_action") is True
    demo = {
        "source_kind": "FUBON_LIVE_FIVE_TIMEFRAME",
        "banner": (
            "自動模擬已啟用・KAM 條件成立後自動模擬執行・禁止真實下單"
            if paper_armed
            else "富邦即時行情・自動模擬未啟用・禁止真實下單"
        ),
        "data_freshness": status,
        "instrument": str(payload.get("symbol", "TMF")),
        "snapshot_time": payload.get("snapshot_written_at", "—"),
        "current_price": five_minute.get("last_price", "—"),
        "u_stage": "U0",
        "cycle_label": (
            "等待有效週期資料" if status != "READY_VERIFIED_FIVE_TIMEFRAMES" else "等待循環位置判讀"
        ),
        "timeframes": tuple(timeframes),
        "timeframe_details": {
            label: dict(analysis.get(key, {}))
            for key, label in _FRAME_LABELS
            if isinstance(analysis.get(key), Mapping)
        },
        "direction": direction,
        "direction_reason": str(summary.get("headline", "依五週期規則持續觀察")),
        "bull_score": str(bull_score),
        "bear_score": str(bear_score),
        "unconfirmed_score": str(unconfirmed_score),
        "trend_health": _RISK_LABELS.get(
            str(summary.get("risk", "unknown")).lower(),
            str(summary.get("risk", "資料驗證中")),
        ),
        "position": f"{open_positions} 口模擬部位" if open_positions else "無模擬部位",
        "unrealized_pnl": str(margin_state.get("unrealized_pnl", "0")),
        "next_step": next_step,
        "automation_mode": "AUTO PAPER" if paper_armed else "未武裝",
    }
    proposal = {
        "模式": "自動模擬" if paper_armed else "關閉",
        "狀態": paper_action_label,
        "KAM 方向": _DIRECTION_LABELS.get(
            str(paper.get("direction", direction)).upper(),
            str(paper.get("direction", direction)),
        ),
        "阻擋原因": "、".join(
            _PAPER_REASON_LABELS.get(str(item), str(item)) for item in paper_reasons
        ) or "—",
        "提案雜湊": str(paper.get("proposal_hash") or "—"),
        "模擬成交價": str(performance.get("entry_price", "—")),
        "自動停損": str(performance.get("stop_loss_price", "—")),
        "自動停利": str(performance.get("take_profit_price", "—")),
        "真單狀態": "必須本人於券商端操作" if real_order_requires_human else "未開放",
    }
    matching = {
        "最近動作": paper_action_label,
        "模擬成交": str(len(paper.get("fill_hashes", ()))),
        "日誌雜湊": str(paper.get("journal_hash") or "—"),
        "目前模擬價": str(performance.get("current_price", "—")),
        "未實現損益": str(margin_state.get("unrealized_pnl", "0")),
        "已實現損益": str(performance.get("realized_pnl", "0")),
        "保證金狀態": _MARGIN_STATUS_LABELS.get(
            str(margin_state.get("status", "no_position")),
            "資料待確認",
        ),
        "LINE 通知": _LINE_ALERT_STATUS_LABELS.get(
            str(paper.get("line_alert_status", "DISABLED")),
            "狀態待確認",
        ),
    }
    ledger = {
        "cash": str(paper.get("cash_balance", "—")),
        "positions": str(open_positions),
        "ledger_hash": str(paper.get("journal_hash") or "—"),
    }
    return PaperTradingOperatorView(
        "KAM 交易決策操作台",
        "富邦即時五週期資料，僅供唯讀決策觀察。",
        proposal,
        matching,
        ledger,
        (),
        False,
        demo=demo,
    )


__all__ = ["build_five_timeframe_operator_view"]
