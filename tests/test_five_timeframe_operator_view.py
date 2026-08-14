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
                "1d": {
                    "ma20": 45700,
                    "price_vs_ma20": "above",
                    "ma20_direction": "rising",
                },
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
    assert "價格相對 20MA：上方（20MA 45,700）" in page
    assert "20MA 方向：上彎" in page
    assert page.count("control-cell unconfirmed") == 6
    assert "風險</dt><dd>不可判讀" in page
    assert "禁止真實下單" in page
    assert "place_order" not in page.lower()
