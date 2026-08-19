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
                    "ma60": 43800,
                    "price_vs_ma60": "above",
                    "ma60_direction": "rising",
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
    assert "三週期狀態" in page
    assert "等待有效週期資料恢復" in page
    assert "TMFH6" in page
    assert "多方 4｜空方 0｜未確認 6" in page
    assert "在20MA上方（45,700）" in page
    assert "價格相對 20MA" not in page
    assert "20MA 方向：上彎" in page
    assert "60MA上方・偏多（43,800）" in page
    assert "20棒壓力：46,500" in page
    assert "20棒支撐：43,000" in page
    assert "偏多觀察・結構待確認" in page
    assert "週線現價</dt><dd>45,920" in page
    assert "週線20MA</dt><dd>41,771" in page
    assert "週線上壓</dt><dd>47,000" in page
    assert "週線下撐</dt><dd>40,000" in page
    assert "cycle-weekly-current" in page and "週現 45,920" in page
    assert "cycle-weekly-ma" in page and "20MA 41,771" in page
    assert "cycle-weekly-resistance" in page and "週壓 47,000" in page
    assert "cycle-weekly-support" in page and "週撐 40,000" in page
    assert "倒 U 以週線現價、20MA、20 棒壓力與支撐作位置參考" in page
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
        "taiex_weekly_cycle": {
            "stage": "U6",
            "label": "起跌形成",
            "source": "TWSE_TAIEX_OFFICIAL_WEEKLY",
            "week_end": "2026-08-14",
            "last_close": "22900",
            "ma20": "23100",
        },
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
        "performance_summary": {
            "sample_size": 12,
            "minimum_sample_size": 30,
            "win_rate": "58.33",
            "expectancy": "42.50",
            "profit_factor": "1.70",
            "maximum_drawdown": "440",
        },
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
    assert "台灣加權指數 TAIEX 週線" in page
    assert "起跌形成" in page
    assert "自動模擬執行" in page
    assert "KAM 買進條件尚未成立" in page
    assert "1000000" in page
    assert "自動停損</dt><dd title='45680'>45680" in page
    assert "自動停利</dt><dd title='45740'>45740" in page
    assert "未實現損益</dt><dd title='150'>150" in page
    assert "保證金狀態</dt><dd title='保證金安全'>保證金安全" in page
    proposal_section = page.split("<section class='proposal'>", 1)[1].split("</section>", 1)[0]
    matching_section = page.split("<section class='matching'>", 1)[1].split("</section>", 1)[0]
    for label in ("Paper 持倉", "停損／停利", "最近動作", "目前模擬價", "未實現損益", "已實現損益", "保證金狀態"):
        assert label in proposal_section
        assert label not in matching_section
    for label in ("目前契約", "行情更新（台灣）", "契約檢查", "實盤狀態"):
        assert label in matching_section
    assert "<span class='line-alert-chip' title='LINE 通知：已啟用・等待模擬提案'>" in page
    assert "<b>LINE 通知</b><strong>已啟用・等待模擬提案</strong>" in page
    assert "class='line-alert-label'" not in page and "class='line-alert-value'" not in page
    assert "<div class='performance-sample'><b>績效樣本</b>" in page
    assert "<small>進度</small><strong>12／30</strong>" in page
    assert "<small>模擬勝率</small><strong>58.33%</strong>" in page
    assert "<small>期望／獲利因子</small><strong>42.50／1.70</strong>" in page
    assert "<small>最大回撤</small><strong>440</strong>" in page
    assert "class='live-order-status-label'>真單狀態</dt><dd class='live-order-status-value' title='必須本人於券商端操作'>必須本人於券商端操作" in page
    assert ">HOLD<" not in page and ">stale<" not in page
    assert view.live_order_allowed is False and view.broker_connected is False


def test_paper_performance_keeps_zero_expectancy_visible() -> None:
    payload = {
        "status": "READY_VERIFIED_FIVE_TIMEFRAMES",
        "symbol": "TMFH6",
        "market_data_only": True,
        "trading_enabled": False,
        "analysis_preview": {"kam_rule_decision": {"direction": "觀望", "states": {}}},
    }
    runtime = {
        "performance_summary": {"expectancy": 0.0, "profit_factor": 0.0},
        "live_order_allowed": False,
        "broker_connected": False,
    }
    page = render_operator_html(
        build_five_timeframe_operator_view(payload, runtime)
    )

    assert "<small>期望／獲利因子</small><strong>0.0／0.0</strong>" in page


def test_operator_shows_self_contained_paper_runtime_diagnostics() -> None:
    payload = {
        "status": "READY_VERIFIED_FIVE_TIMEFRAMES",
        "symbol": "TMFI6",
        "snapshot_written_at": "2026-08-19T05:52:31+00:00",
        "market_data_only": True,
        "trading_enabled": False,
        "analysis_preview": {"kam_rule_decision": {"direction": "SHORT", "states": {}}},
    }
    runtime = {
        "instrument": "TMFI6",
        "armed": True,
        "open_positions": 1,
        "quote_observed_at": "2026-08-19T05:53:00+00:00",
        "journal_integrity_status": "VERIFIED",
        "performance_event": {
            "instrument": "TMFI6",
            "stop_loss_price": "44535",
            "take_profit_price": "44495",
        },
        "live_order_allowed": False,
        "broker_connected": False,
        "execution_boundary": {
            "broker_submission_available": False,
            "live_order_allowed": False,
        },
    }

    view = build_five_timeframe_operator_view(payload, runtime)
    page = render_operator_html(view)

    assert view.matching["目前契約"] == "TMFI6"
    assert view.matching["行情更新（台灣）"] == "2026-08-19 13:53:00"
    assert view.matching["Paper 持倉"] == "1 口・TMFI6"
    assert view.matching["停損／停利"] == "44535／44495"
    assert view.matching["契約檢查"] == "一致"
    assert view.matching["日誌驗證"] == "正常"
    assert view.matching["實盤狀態"] == "永久鎖定・禁止下單"
    assert "永久鎖定・禁止下單" in page
    assert view.live_order_allowed is False


def test_operator_warns_when_open_paper_position_contract_differs_from_quote() -> None:
    payload = {
        "status": "READY_VERIFIED_FIVE_TIMEFRAMES",
        "symbol": "TMFI6",
        "market_data_only": True,
        "trading_enabled": False,
        "analysis_preview": {"kam_rule_decision": {"states": {}}},
    }
    runtime = {
        "instrument": "TMFH6",
        "open_positions": 1,
        "live_order_allowed": False,
        "broker_connected": False,
        "execution_boundary": {"broker_submission_available": False},
    }

    view = build_five_timeframe_operator_view(payload, runtime)

    assert view.matching["契約檢查"] == "異常：持倉 TMFH6／行情 TMFI6"
    assert view.live_order_allowed is False


def test_operator_prioritizes_m15_trendline_weakening_warning() -> None:
    payload = {
        "status": "READY_VERIFIED_FIVE_TIMEFRAMES",
        "symbol": "TMFH6",
        "market_data_only": True,
        "trading_enabled": False,
        "analysis_preview": {
            "three_second_summary": {"headline": "五週期分析已更新"},
            "decision_diagnostics": {
                "trend_warning_codes": [
                    "M15_ASCENDING_TRENDLINE_BROKEN_WEAKENING"
                ]
            },
            "kam_rule_decision": {
                "direction": "LONG",
                "primary_next_action": "等待",
                "states": {},
            },
        },
    }

    view = build_five_timeframe_operator_view(payload)
    page = render_operator_html(view)

    assert "15分上升趨勢線跌破・注意可能轉弱" in page


def test_operator_prioritizes_daily_descending_trendline_weakening() -> None:
    payload = {
        "status": "READY_VERIFIED_FIVE_TIMEFRAMES",
        "symbol": "TMFH6",
        "market_data_only": True,
        "trading_enabled": False,
        "analysis_preview": {
            "three_second_summary": {"headline": "五週期分析已更新"},
            "decision_diagnostics": {"daily_bullish_weakening": True},
            "kam_rule_decision": {
                "direction": "SHORT",
                "primary_next_action": "等待",
                "states": {},
                "paper_test_direction": {
                    "reason_code": (
                        "D1_DESCENDING_TRENDLINE_WEAKENING_M60_M15_SHORT_TRIGGER"
                    )
                },
            },
        },
    }

    view = build_five_timeframe_operator_view(payload)
    page = render_operator_html(view)

    assert "日線下降趨勢線壓制・多方轉弱・空方條件加強" in page
    assert view.live_order_allowed is False


def test_operator_distinguishes_general_short_waiting_for_daily_confirmation() -> None:
    payload = {
        "status": "READY_VERIFIED_FIVE_TIMEFRAMES",
        "symbol": "TMFH6",
        "market_data_only": True,
        "trading_enabled": False,
        "analysis_preview": {
            "three_second_summary": {"headline": "五週期分析已更新"},
            "decision_diagnostics": {"daily_bullish_weakening": False},
            "kam_rule_decision": {
                "direction": "SHORT",
                "primary_next_action": "等待",
                "states": {},
                "paper_test_direction": {
                    "reason_code": "M60_BEARISH_M15_SHORT_TRIGGER",
                    "short_setup_grade": "waiting_daily_confirmation",
                },
            },
        },
    }

    view = build_five_timeframe_operator_view(payload)

    assert view.demo is not None
    assert view.demo["next_step"] == "一般空單成立・等待日線下降趨勢線確認"
    assert view.live_order_allowed is False



def test_operator_explains_exact_ma_and_alignment_blockers_in_chinese() -> None:
    payload = {
        "status": "READY_VERIFIED_FIVE_TIMEFRAMES",
        "symbol": "TMFH6",
        "market_data_only": True,
        "trading_enabled": False,
        "analysis_preview": {
            "three_second_summary": {"headline": "五週期分析已更新"},
            "kam_rule_decision": {
                "direction": "HOLD",
                "primary_next_action": "等待",
                "states": {},
                "paper_test_direction": {
                    "direction": "HOLD",
                    "reason_code": "M15_MA20_LONG_TRIGGER_NOT_CONFIRMED",
                    "eligible": False,
                },
            },
        },
    }

    view = build_five_timeframe_operator_view(payload)
    page = render_operator_html(view)

    message = "15分尚未站上20MA且20MA未上彎・等待多單確認"
    assert view.demo is not None
    assert view.demo["direction_reason"] == message
    assert view.demo["next_step"] == message
    assert page.count(message) >= 2
    assert view.live_order_allowed is False


def test_operator_assigns_one_control_vote_to_intact_m60_ma20_support() -> None:
    payload = {
        "status": "READY_VERIFIED_FIVE_TIMEFRAMES",
        "symbol": "TMFI6",
        "market_data_only": True,
        "trading_enabled": False,
        "analysis_preview": {
            "three_second_summary": {"headline": "五週期分析已更新", "direction": "觀望"},
            "decision_diagnostics": {
                "m60_ma20_support": "retest_held",
                "m60_market_bias": "bullish",
            },
            "kam_rule_decision": {
                "direction": "HOLD",
                "primary_next_action": "等待五週期確認",
                "states": {
                    "1w": {"code": "ND"},
                    "1d": {"code": "NF"},
                    "60m": {"code": "AU"},
                    "15m": {"code": "AF"},
                    "5m": {"code": "NU"},
                },
            },
            "timeframes": {"5m": {"last_price": 46137}},
        },
    }

    view = build_five_timeframe_operator_view(payload)
    page = render_operator_html(view)

    assert view.demo is not None
    assert view.demo["direction"] == "偏多"
    assert view.demo["direction_reason"] == "60分20MA支撐未破・行情偏多看待"
    assert view.demo["bull_score"] == "60"
    assert view.demo["bear_score"] == "0"
    assert view.demo["unconfirmed_score"] == "40"
    assert "多方 6｜空方 0｜未確認 4" in page
    assert view.live_order_allowed is False
