"""Project a safe five-timeframe snapshot into the canonical KAM operator UI."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

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
    "CONSECUTIVE_STOP_LOSS_LIMIT_REACHED": "連續兩次停損・本交易日停止進場",
    "QUOTE_STALE": "行情資料過期",
    "ENTRY_CONFIRMATION_PENDING": "等待下一根 5 分 K 確認",
    "ENTRY_PRICE_CONFIRMATION_PENDING": "短線尚未延續・重新等待確認",
    "ENTRY_CONFIRMATION_MOVE_TOO_LARGE": "短線跳動過大・避免追價",
    "TREND_HOLD_TAKE_PROFIT_EXTENDED": "方向持續一致・已順勢延伸停利",
    "STRUCTURAL_STOP_TESTED_WAITING_FOR_5M_CLOSE": "波浪結構受測・等待五分鐘收盤確認",
    "DAILY_MA60_NOT_BULLISH": "日線尚未站上60MA・不建立多單",
    "DAILY_MA60_NOT_BEARISH": "日線尚未跌破60MA・不建立空單",
    "M15_TREND_WEAKENING_WARNING": "15分趨勢線警示・注意可能轉弱",
    "M15_MA20_RULE_EXIT": "15分20MA條件失效・模擬部位已平倉",
    "M15_MA20_LONG_TRIGGER_NOT_CONFIRMED": "15分尚未站上20MA且20MA未上彎・等待多單確認",
    "M15_MA20_SHORT_TRIGGER_NOT_CONFIRMED": "15分尚未跌破20MA且20MA未下彎・等待空單確認",
    "M60_MA20_SUPPORT_BULLISH_BIAS": "60分20MA支撐未破・行情偏多・不建立空單",
    "M60_MA20_SUPPORT_BROKEN": "60分K收破20MA支撐・多方轉弱・不建立多單",
    "M60_BULLISH_M15_LONG_TRIGGER": "60分位置偏多・15分多單條件成立",
    "M60_BEARISH_M15_SHORT_TRIGGER": "60分位置偏空・15分空單條件成立",
    "D1_DESCENDING_TRENDLINE_WEAKENING_M60_M15_SHORT_TRIGGER": (
        "日線下降趨勢線確認多方轉弱・60分與15分空單條件成立"
    ),
    "M60_LOCATION_INSUFFICIENT": "60分位置資料不足・暫不進場",
    "M60_LOCATION_NOT_DIRECTIONAL": "60分位置尚未形成明確多空方向",
    "FIVE_TIMEFRAME_NOT_FULLY_ALIGNED": "五週期方向尚未一致・維持觀望",
}
_LINE_ALERT_STATUS_LABELS = {
    "DISABLED": "未啟用",
    "ARMED_WAITING_FOR_PAPER_PROPOSAL": "已啟用・等待模擬提案",
    "SENT": "已傳送",
    "EXIT_SENT": "平倉通知已傳送",
    "WAITING_OR_DUPLICATE": "等待下一階段",
    "RETRY_PENDING": "傳送失敗・等待重試",
    "ROLLOVER_SENT": "換倉提醒已傳送",
    "ANALYSIS_SENT": "現況分析已傳送",
}


def _taiwan_time(value: object) -> str:
    if value in (None, "", "—"):
        return "—"
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return str(value)
    if parsed.tzinfo is None:
        return str(value)
    return parsed.astimezone(ZoneInfo("Asia/Taipei")).strftime("%Y-%m-%d %H:%M:%S")


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
    diagnostics = preview.get("decision_diagnostics")
    diagnostics = diagnostics if isinstance(diagnostics, Mapping) else {}
    paper_test_direction = decision.get("paper_test_direction")
    paper_test_direction = (
        paper_test_direction if isinstance(paper_test_direction, Mapping) else {}
    )
    decision_reason_code = str(paper_test_direction.get("reason_code", ""))
    decision_blocker = _PAPER_REASON_LABELS.get(decision_reason_code, "")
    trend_warnings = diagnostics.get("trend_warning_codes", ())
    trend_warnings = trend_warnings if isinstance(trend_warnings, (list, tuple)) else ()
    daily_weakening = diagnostics.get("daily_bullish_weakening") is True
    short_setup_grade = str(paper_test_direction.get("short_setup_grade", ""))
    weakening_message = (
        "日線下降趨勢線壓制・多方轉弱・空方條件加強"
        if daily_weakening
        else "一般空單成立・等待日線下降趨勢線確認"
        if short_setup_grade == "waiting_daily_confirmation"
        else "一般空單成立・日線下降線尚未形成"
        if short_setup_grade == "general_intraday"
        else "15分上升趨勢線跌破・注意可能轉弱"
        if "M15_ASCENDING_TRENDLINE_BROKEN_WEAKENING" in trend_warnings
        else "15分波浪反彈碰下降趨勢線・注意可能轉弱"
        if "M15_DESCENDING_TRENDLINE_RESISTANCE_WEAKENING" in trend_warnings
        else ""
    )
    states = decision.get("states")
    states = states if isinstance(states, Mapping) else {}
    analysis = preview.get("timeframes")
    analysis = analysis if isinstance(analysis, Mapping) else {}
    five_minute = analysis.get("5m")
    five_minute = five_minute if isinstance(five_minute, Mapping) else {}
    sixty_minute = analysis.get("60m")
    sixty_minute = sixty_minute if isinstance(sixty_minute, Mapping) else {}
    if decision_reason_code == "M60_LOCATION_INSUFFICIENT":
        closed_count = int(sixty_minute.get("closed_candle_count", 0) or 0)
        required_count = int(sixty_minute.get("required_candle_count", 20) or 20)
        decision_blocker = (
            f"60分官方歷史補足中・已完成 {closed_count}／{required_count} 根"
        )

    m60_bias = str(diagnostics.get("m60_market_bias", "insufficient"))
    m60_bias_message = (
        "60分20MA支撐未破・行情偏多看待"
        if m60_bias == "bullish"
        else "60分K收破20MA支撐・多方轉弱"
        if m60_bias == "bearish"
        else ""
    )
    raw_direction = str(decision.get("direction", summary.get("direction", "觀望")))
    direction = _DIRECTION_LABELS.get(raw_direction.upper(), raw_direction)
    if direction == "觀望" and m60_bias == "bullish":
        direction = "偏多"
    elif direction == "觀望" and m60_bias == "bearish":
        direction = "偏空"
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
    if m60_bias == "bullish":
        bull_score = min(100, bull_score + 20)
        if unconfirmed_score >= 20:
            unconfirmed_score -= 20
        else:
            bear_score = max(0, bear_score - 20)
    elif m60_bias == "bearish":
        bear_score = min(100, bear_score + 20)
        if unconfirmed_score >= 20:
            unconfirmed_score -= 20
        else:
            bull_score = max(0, bull_score - 20)

    status = str(payload.get("status", "資料不足"))
    next_step = (
        weakening_message
        or decision_blocker
        or m60_bias_message
        or str(decision.get("primary_next_action", summary.get("next_step", "等待資料完整")))
    )
    paper = paper_runtime if isinstance(paper_runtime, Mapping) else {}
    taiex_cycle = paper.get("taiex_weekly_cycle")
    taiex_cycle = taiex_cycle if isinstance(taiex_cycle, Mapping) else {}
    paper_armed = paper.get("armed") is True
    paper_action = str(paper.get("action", "WAITING_FOR_KAM" if paper_armed else "DISARMED"))
    paper_action_label = _PAPER_ACTION_LABELS.get(paper_action, paper_action)
    paper_reasons = paper.get("reason_codes", ())
    if not isinstance(paper_reasons, (list, tuple)):
        paper_reasons = ()
    open_positions = int(paper.get("open_positions", 0) or 0)
    performance = paper.get("performance_event")
    performance = performance if isinstance(performance, Mapping) else {}
    if paper_action == "exit_filled":
        exit_type = str(performance.get("event_type", ""))
        realized = Decimal(str(performance.get("realized_pnl", "0") or "0"))
        if exit_type == "stop_loss_exit" and realized > 0:
            paper_action_label = "移動停損鎖利出場"
        elif exit_type == "stop_loss_exit":
            paper_action_label = "風險停損出場"
        elif exit_type == "take_profit_exit":
            paper_action_label = "目標停利出場"
        elif exit_type == "m15_ma20_rule_exit":
            paper_action_label = "趨勢規則出場"
    margin_state = paper.get("margin_state")
    margin_state = margin_state if isinstance(margin_state, Mapping) else {}
    performance_summary = paper.get("performance_summary")
    performance_summary = performance_summary if isinstance(performance_summary, Mapping) else {}
    opportunity_summary = paper.get("opportunity_summary")
    opportunity_summary = opportunity_summary if isinstance(opportunity_summary, Mapping) else {}
    wave_stop_comparison = paper.get("wave_stop_comparison")
    wave_stop_comparison = (
        wave_stop_comparison if isinstance(wave_stop_comparison, Mapping) else {}
    )
    execution_boundary = paper.get("execution_boundary")
    execution_boundary = execution_boundary if isinstance(execution_boundary, Mapping) else {}
    current_analysis = paper.get("current_analysis")
    current_analysis = current_analysis if isinstance(current_analysis, Mapping) else {}
    current_symbol = str(payload.get("symbol", "TMF"))
    paper_instrument = str(
        performance.get("instrument") or paper.get("instrument") or current_symbol
    )
    contract_consistency = (
        "一致"
        if not open_positions or paper_instrument == current_symbol
        else f"異常：持倉 {paper_instrument}／行情 {current_symbol}"
    )
    execution_safe = (
        paper.get("live_order_allowed") is not True
        and paper.get("broker_connected") is not True
        and execution_boundary.get("broker_submission_available") is not True
    )
    demo = {
        "source_kind": "FUBON_LIVE_FIVE_TIMEFRAME",
        "banner": (
            "自動模擬已啟用・KAM 條件成立後自動模擬執行・禁止真實下單"
            if paper_armed
            else "富邦即時行情・自動模擬未啟用・禁止真實下單"
        ),
        "data_freshness": status,
        "instrument": current_symbol,
        "snapshot_time": payload.get("snapshot_written_at", "—"),
        "current_price": five_minute.get("last_price", "—"),
        "u_stage": str(taiex_cycle.get("stage", "U0")),
        "cycle_label": str(taiex_cycle.get("label")) if taiex_cycle else (
            "等待有效週期資料" if status != "READY_VERIFIED_FIVE_TIMEFRAMES" else "等待循環位置判讀"
        ),
        "cycle_source": "台灣加權指數 TAIEX 週線",
        "cycle_week_end": taiex_cycle.get("week_end", "—"),
        "cycle_last_close": taiex_cycle.get("last_close", "—"),
        "cycle_ma20": taiex_cycle.get("ma20", "—"),
        "timeframes": tuple(timeframes),
        "timeframe_details": {
            label: dict(analysis.get(key, {}))
            for key, label in _FRAME_LABELS
            if isinstance(analysis.get(key), Mapping)
        },
        "direction": direction,
        "direction_reason": (
            weakening_message
            or decision_blocker
            or m60_bias_message
            or str(summary.get("headline", "依五週期規則持續觀察"))
        ),
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
        "current_analysis": dict(current_analysis),
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
        "機會等級": (
            f"{paper_test_direction.get('opportunity_grade')}級"
            if paper_test_direction.get("opportunity_grade")
            else "等待"
        ),
        "尚差條件": str(paper_test_direction.get("missing_condition") or "已完成"),
        "提前觸發": str(paper_test_direction.get("early_trigger") or "尚未形成"),
        "回踩位置": str(paper_test_direction.get("pullback_reference") or "—"),
        "影子統計": (
            f"30點 {opportunity_summary.get('reached_30_points', 0)}／"
            f"60點 {opportunity_summary.get('reached_60_points', 0)}／"
            f"120點 {opportunity_summary.get('reached_120_points', 0)}"
        ),
        "模擬成交價": str(performance.get("entry_price", "—")),
    }
    stop_value = performance.get("stop_loss_price")
    entry_value = performance.get("entry_price")
    emergency_stop = "—"
    if open_positions and stop_value is not None and entry_value is not None:
        try:
            stop_number = Decimal(str(stop_value))
            entry_number = Decimal(str(entry_value))
            emergency_stop = str(
                stop_number - Decimal("20")
                if stop_number < entry_number
                else stop_number + Decimal("20")
            )
        except Exception:
            emergency_stop = "—"
    structural_waiting = "STRUCTURAL_STOP_TESTED_WAITING_FOR_5M_CLOSE" in {
        str(item) for item in paper_reasons
    }
    matching = {
        "目前契約": current_symbol,
        "行情更新（台灣）": _taiwan_time(
            paper.get("quote_observed_at") or payload.get("snapshot_written_at")
        ),
        "Paper 持倉": (
            f"{open_positions} 口・{paper_instrument}"
            if open_positions
            else "無持倉"
        ),
        "停損／停利": (
            f"{performance.get('stop_loss_price', '—')}／"
            f"{performance.get('take_profit_price', '—')}"
        ),
        "風控狀態": (
            "波浪結構受測・等待五分鐘收盤確認"
            if structural_waiting
            else "持倉中・依波浪結構保護"
            if open_positions
            else "目前無部位"
        ),
        "結構警戒": str(stop_value if open_positions and stop_value is not None else "—"),
        "五分鐘確認": (
            f"收盤越過 {stop_value} 才出場"
            if open_positions and stop_value is not None
            else "—"
        ),
        "緊急停損": emergency_stop,
        "第一目標": str(
            performance.get("take_profit_price", "—") if open_positions else "—"
        ),
        "契約檢查": contract_consistency,
        "日誌驗證": (
            "正常"
            if paper.get("journal_integrity_status") == "VERIFIED"
            else "等待首次驗證"
            if not paper.get("journal_integrity_status")
            else "異常・已停止模擬處理"
        ),
        "實盤狀態": "永久鎖定・禁止下單" if execution_safe else "安全邊界待確認",
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
        "績效樣本": (
            f"{performance_summary.get('sample_size', 0)}／"
            f"{performance_summary.get('minimum_sample_size', 30)}"
        ),
        "累計損益": str(performance_summary.get("net_pnl", "0")),
        "勝敗／勝率": (
            "—"
            if performance_summary.get("win_rate") is None
            else (
                f"{performance_summary.get('wins', 0)}勝"
                f"{performance_summary.get('losses', 0)}敗・"
                f"{performance_summary['win_rate']}%"
            )
        ),
        "均賺／均賠": (
            f"{performance_summary.get('average_win', '—') if performance_summary.get('average_win') is not None else '—'}／"
            f"{performance_summary.get('average_loss', '—') if performance_summary.get('average_loss') is not None else '—'}"
        ),
        "獲利因子／回撤": (
            f"{performance_summary.get('profit_factor', '—') if performance_summary.get('profit_factor') is not None else '—'}／"
            f"{performance_summary.get('maximum_drawdown', '0')}"
        ),
        "停損品質": str(performance_summary.get("stop_quality", "持續累積比較樣本")),
        "獲利保留": (
            "—"
            if performance_summary.get("profit_retention_rate") is None
            else f"{performance_summary['profit_retention_rate']}%"
        ),
        "固定停損比較": (
            "尚無差異"
            if not performance_summary.get("shadow_avoided_premature_exits")
            else (
                f"避免 {performance_summary['shadow_avoided_premature_exits']} 次過早出場・"
                f"改善 {performance_summary.get('shadow_incremental_pnl', '0')}"
            )
        ),
        "影子停損比較": (
            f"{wave_stop_comparison.get('verdict', '樣本不足')}・"
            f"固定 {wave_stop_comparison.get('fixed_stop_exits', 0)}／"
            f"波浪 {wave_stop_comparison.get('wave_stop_exits', 0)}／"
            f"避開誤洗 {wave_stop_comparison.get('saved_by_wave_stop', 0)}"
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
