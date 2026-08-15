from kam_market_ai.live_read_only.five_timeframe_operator_view import (
    build_five_timeframe_operator_view,
)
from kam_market_ai.paper_trading.operator_wsgi import render_operator_html


def test_live_five_timeframe_uses_established_kam_operator_ui() -> None:
    payload = {
        "status": "ATTESTATION_REQUIRED",
        "symbol": "TMFH6",
        "market_data_only": True,
        "trading_enabled": False,
        "analysis_preview": {
            "three_second_summary": {"headline": "日週線形成中", "direction": "觀望"},
            "timeframes": {
                "1w": {
                    "status": "ambiguous",
                    "position": "bullish",
                    "trend": "bullish",
                    "ma20": 41771.05,
                    "range_resistance": 47000,
                    "range_support": 40000,
                    "range_window_bars": 20,
                },
                "1d": {
                    "ma20": 45700,
                    "price_vs_ma20": "above",
                    "ma20_direction": "rising",
                    "range_resistance": 46500,
                    "range_support": 43000,
                    "range_window_bars": 20,
                },
                "60m": {
                    "ma20": 45582.45,
                    "price_vs_ma20": "above",
                    "ma20_direction": "rising",
                    "range_resistance": 46100,
                    "range_support": 45500,
                    "range_window_bars": 20,
                },
                "15m": {
                    "ma20": 45889.60,
                    "price_vs_ma20": "above",
                    "ma20_direction": "rising",
                    "range_resistance": 45950,
                    "range_support": 45800,
                    "range_window_bars": 20,
                },
                "5m": {"last_price": 45920},
            },
            "kam_rule_decision": {
                "direction": "觀望",
                "primary_next_action": "等待有效週期資料恢復",
                "states": {
                    "1w": {"code": "ND"},
                    "1d": {"code": "NF"},
                    "60m": {"code": "AU"},
                    "15m": {"code": "AF"},
                    "5m": {"code": "NU"},
                },
            },
        },
    }

    view = build_five_timeframe_operator_view(payload)
    page = render_operator_html(view)

    assert view.read_only is True
    assert view.live_order_allowed is False
    assert "KAM 交易決策操作台" in page
    assert "多空控制權" in page
    assert "市場循環位置" in page
    assert "四週期狀態" in page
    assert "等待有效週期資料恢復" in page
    assert "TMFH6" in page
    assert "多方 4｜空方 0｜未確認 6" in page
    assert "在20MA上方（45,700）" in page
    assert "價格相對 20MA" not in page
    assert "20MA 方向：上彎" in page
    assert "20棒壓力：46,500" in page
    assert "20棒支撐：43,000" in page
    assert "偏多觀察・結構待確認" in page
    assert "即時微台</dt><dd>45,920" in page
    assert "60分20MA</dt><dd>45,582（現價在上・上彎）" in page
    assert "最近上壓</dt><dd>45,950（15分／+30點）" in page
    assert "最近下撐</dt><dd>45,800（15分／−120點）" in page
    assert "壓力／支撐為 20 棒區間參考，不是買賣訊號" in page
    assert page.count("control-cell unconfirmed") == 6
    assert "風險</dt><dd>不可判讀" in page
    assert "禁止真實下單" in page
    assert "place_order" not in page.lower()


def test_market_dashboard_exposes_armed_auto_paper_runtime_without_live_execution() -> None:
    payload = {
        "status": "READY_VERIFIED_FIVE_TIMEFRAMES",
        "symbol": "TMFH6",
        "market_data_only": True,
        "trading_enabled": False,
        "analysis_preview": {"kam_rule_decision": {"direction": "觀望", "states": {}}},
    }
    runtime = {
        "armed": True,
        "action": "hold",
        "direction": "HOLD",
        "reason_codes": ["KAM_BUY_CONDITION_NOT_MET"],
        "cash_balance": "1000000",
        "open_positions": 0,
        "journal_hash": "a" * 64,
        "proposal_hash": None,
        "fill_hashes": [],
        "margin_state": {
            "unrealized_pnl": "150",
            "status": "safe",
        },
        "line_alert_status": "ARMED_WAITING_FOR_PAPER_PROPOSAL",
        "performance_event": {
            "entry_price": "45700",
            "current_price": "45715",
            "stop_loss_price": "45680",
            "take_profit_price": "45740",
            "realized_pnl": "0",
        },
        "live_order_allowed": False,
        "broker_connected": False,
        "execution_boundary": {
            "mode": "paper_only",
            "automatic_paper_execution": True,
            "real_order_requires_human_action": True,
            "broker_submission_available": False,
            "live_order_allowed": False,
        },
    }

    view = build_five_timeframe_operator_view(payload, runtime)
    page = render_operator_html(view)

    assert "自動模擬已啟用" in page
    assert "自動模擬執行" in page
    assert "KAM 買進條件尚未成立" in page
    assert "1000000" in page
    assert "自動停損</dt><dd title='45680'>45680" in page
    assert "自動停利</dt><dd title='45740'>45740" in page
    assert "未實現損益</dt><dd title='150'>150" in page
    assert "保證金狀態</dt><dd title='保證金安全'>保證金安全" in page
    assert "LINE 通知</dt><dd title='已啟用・等待模擬提案'>已啟用・等待模擬提案" in page
    assert "真單狀態</dt><dd title='必須本人於券商端操作'>必須本人於券商端操作" in page
    assert ">HOLD<" not in page and ">stale<" not in page
    assert view.live_order_allowed is False and view.broker_connected is False
