from kam_market_ai.paper_trading.demo_proposal import build_demo_session
from kam_market_ai.paper_trading.demo_snapshot import DEMO_SNAPSHOT
from kam_market_ai.paper_trading.operator_presenter import build_demo_operator_presenter
from kam_market_ai.paper_trading.operator_wsgi import render_operator_html


def test_demo_is_explicitly_labelled_fixed_offline_data_and_renders_full_flow() -> None:
    proposal, matching = build_demo_session()
    view = build_demo_operator_presenter(proposal, matching, DEMO_SNAPSHOT)
    html = render_operator_html(view)
    for text in (
        "離線示範行情",
        "唯讀模式",
        "禁止真實下單",
        "決策呈現已切換；模擬委託流程尚未接入此商品 snapshot。",
        "倒 U 階段",
        "五週期狀態",
        "唯一下一步",
        "模擬委託建議",
        "模擬撮合結果",
        "模擬現金",
        "稽核紀錄",
    ):
        assert text in html
    assert "real-time" not in html.lower() and "live market" not in html.lower()
    assert view.live_order_allowed is False and view.broker_connected is False and view.dry_run is True
    assert DEMO_SNAPSHOT.data_freshness == "DEMO" and len(DEMO_SNAPSHOT.timeframes) == 5
