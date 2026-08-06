from kam_market_ai.paper_trading.operator_presenter import PaperTradingOperatorView
from kam_market_ai.paper_trading.operator_wsgi import build_operator_wsgi
from kam_market_ai.public_deployment import PublicEmbedConfig


def _app(config=None):
    return build_operator_wsgi(lambda: PaperTradingOperatorView("KAM", "", {}, {}, {"cash": "0"}, (), False), public_embed_config=config)


def _request(app, path, method="GET", query=""):
    response = {}
    body = b"".join(app({"REQUEST_METHOD": method, "PATH_INFO": path, "QUERY_STRING": query}, lambda status, headers: response.update(status=status, headers=dict(headers))))
    return response, body.decode("utf-8")


def test_health_and_ready_are_get_only_and_have_public_security_headers():
    app = _app()
    health, body = _request(app, "/healthz")
    assert health["status"] == "200 OK" and '"status":"ok"' in body
    assert "frame-ancestors 'self'" in health["headers"]["Content-Security-Policy"]
    assert health["headers"]["X-Content-Type-Options"] == "nosniff"
    ready, _ = _request(app, "/readyz")
    assert ready["status"] == "200 OK"
    post, _ = _request(app, "/healthz", method="POST")
    assert post["status"] == "405 Method Not Allowed"


def test_embed_uses_selected_snapshot_and_can_be_disabled():
    app = _app()
    response, html = _request(app, "/embed", query="instrument=TX")
    assert response["status"] == "200 OK" and "TXF202609" in html and "/embed?instrument=TMF" in html
    assert "唯讀模式" in html and "禁止真實下單" in html
    disabled, _ = _request(_app(PublicEmbedConfig(enable_embed=False)), "/embed")
    assert disabled["status"] == "404 Not Found"
    post, _ = _request(app, "/embed", method="POST")
    assert post["status"] == "405 Method Not Allowed"
