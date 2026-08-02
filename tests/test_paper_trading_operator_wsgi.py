from datetime import UTC, datetime

from kam_market_ai.paper_trading.operator_presenter import PaperTradingOperatorView
from kam_market_ai.paper_trading.operator_wsgi import build_operator_wsgi, render_operator_html


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
