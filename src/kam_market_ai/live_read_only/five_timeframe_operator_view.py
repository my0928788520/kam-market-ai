"""Project a safe five-timeframe snapshot into the canonical KAM operator UI."""

from __future__ import annotations

from collections.abc import Mapping

from kam_market_ai.paper_trading.operator_presenter import PaperTradingOperatorView


_FRAME_LABELS = (("1w", "週線"), ("1d", "日線"), ("60m", "60 分"), ("15m", "15 分"), ("5m", "5 分"))


def build_five_timeframe_operator_view(payload: Mapping[str, object]) -> PaperTradingOperatorView:
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

    direction = str(decision.get("direction", summary.get("direction", "觀望")))
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
    bull_score = 50 if bull == bear else round(100 * bull / max(1, bull + bear))

    status = str(payload.get("status", "資料不足"))
    next_step = str(decision.get("primary_next_action", summary.get("next_step", "等待資料完整")))
    demo = {
        "source_kind": "FUBON_LIVE_FIVE_TIMEFRAME",
        "banner": "富邦即時行情・KAM 五週期唯讀分析・禁止真實下單",
        "data_freshness": status,
        "instrument": str(payload.get("symbol", "TMF")),
        "snapshot_time": payload.get("snapshot_written_at", "—"),
        "current_price": "—",
        "u_stage": "U0",
        "cycle_label": "等待有效週期資料" if status != "READY_VERIFIED_FIVE_TIMEFRAMES" else "五週期已驗證",
        "timeframes": tuple(timeframes),
        "direction": direction,
        "direction_reason": str(summary.get("headline", "依五週期規則持續觀察")),
        "bull_score": str(bull_score),
        "bear_score": str(100 - bull_score),
        "trend_health": str(summary.get("risk", "資料驗證中")),
        "position": "無部位（唯讀）",
        "unrealized_pnl": "—",
        "next_step": next_step,
    }
    return PaperTradingOperatorView(
        "KAM 交易決策操作台",
        "富邦即時五週期資料，僅供唯讀決策觀察。",
        {"status": "唯讀觀察", "action": "不建立委託"},
        {"state": "未執行", "fills": "0"},
        {"cash": "—", "positions": "—"},
        (),
        False,
        demo=demo,
    )


__all__ = ["build_five_timeframe_operator_view"]
