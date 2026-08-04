from datetime import UTC, datetime
from pathlib import Path

from kam_market_ai.paper_trading.operator_presenter import PaperTradingOperatorView
from kam_market_ai.paper_trading.operator_wsgi import build_operator_wsgi, render_operator_html
from kam_market_ai.paper_trading.demo_proposal import build_demo_session
from kam_market_ai.paper_trading.demo_snapshot import DEMO_SNAPSHOT
from kam_market_ai.paper_trading.operator_presenter import build_demo_operator_presenter


def _view() -> PaperTradingOperatorView:
    return PaperTradingOperatorView("<KAM>", "安全", {"instrument": "TEST"}, {"state": "等待中"}, {"cash": "100"}, (), False)


def test_wsgi_is_get_only_escapes_html_and_serves_static_css() -> None:
    app = build_operator_wsgi(_view); response = {}
    def start(status, headers): response.update(status=status, headers=headers)
    body = b"".join(app({"REQUEST_METHOD": "GET", "PATH_INFO": "/"}, start)).decode()
    assert response["status"] == "200 OK" and "&lt;KAM&gt;" in body and "lang='zh-Hant-TW'" in body
    assert "唯讀模式・模擬執行・禁止真實下單" in body and "Paper Order Proposal" not in body
    assert b"".join(app({"REQUEST_METHOD": "POST", "PATH_INFO": "/"}, start)) == "唯讀端點，不接受此操作。".encode("utf-8")
    assert response["status"] == "405 Method Not Allowed"
    assert b"body" in b"".join(app({"REQUEST_METHOD": "GET", "PATH_INFO": "/static/operator.css"}, start))
    assert "<KAM>" not in render_operator_html(_view())


def test_dashboard_renders_real_control_cells_and_coloured_cycle_structure() -> None:
    proposal, matching = build_demo_session()
    view = build_demo_operator_presenter(proposal, matching, DEMO_SNAPSHOT)
    html = render_operator_html(view)

    assert "多方 6｜空方 4" in html
    assert "多方 62" not in html and "空方 38" not in html
    assert "控制權分裂" in html
    assert html.count("class='control-cell ") == 10
    assert html.count("control-cell bull") == 6
    assert html.count("control-cell bear") == 4
    assert html.index("control-cell bear") > html.index("control-cell bull")
    assert "class='cycle-info'" in html
    assert "市場循環位置" in html
    assert "rise-path" in html and "fall-path" in html
    assert "linearGradient id='cycle-rise'" in html and "linearGradient id='cycle-fall'" in html
    assert "filter id='cycle-glow'" in html and "filter id='cycle-marker-glow'" in html
    assert "class='cycle-marker'" in html and "transform='translate(150 59)'" in html
    assert "preserveAspectRatio='xMidYMid meet'" in html
    for field in ("目前位置", "循環狀態", "上一階段", "下一階段", "唯一下一步", "風險"):
        assert field in html
    for state_code in ("AU", "NF", "NU"):
        assert state_code in html
    for footer_field in ("已實現損益", "未實現損益", "緊急停止"):
        assert footer_field in html
    for label in ("低檔確認", "起漲形成", "多方延伸", "高檔回落", "起跌形成", "空方延伸", "低點止跌"):
        assert label in html


def test_desktop_layout_contract_prevents_page_scrolling_without_card_scrollers() -> None:
    css = Path("src/kam_market_ai/paper_trading/static/operator.css").read_text(encoding="utf-8")

    assert '@import "../../ui/design_tokens.css"' in css
    assert "height: 100vh" in css and "overflow: hidden" in css
    assert "grid-template-rows: minmax(160px, 205px) minmax(110px, 128px) minmax(96px, 110px) minmax(0, 1fr)" in css
    assert "footer { grid-row: 4; position: static;" in css
    assert ".cycle-chart svg" in css and "height: 180px" in css
    assert "marker-breathe 5s" in css
    assert ".proposal dd, .matching dd" in css and "text-overflow: ellipsis" in css
    assert "justify-content: center" in css and "border-radius: 7px" in css
    bull_rule = css.split(".control-cell.bull", 1)[1].split(".control-cell.bear", 1)[0]
    bear_rule = css.split(".control-cell.bear", 1)[1]
    assert "#e63357" in bull_rule and "#b51f40" in bull_rule
    assert "#2fca9d" in bear_rule and "#19866e" in bear_rule
    assert "0 0 10px" in bull_rule and "0 3px 6px" not in bull_rule
    assert "transform: none" in css and "inset 0 -2px" not in css
    assert ".control-cell::before" not in css and ".control-cell::after" not in css
