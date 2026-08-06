from json import loads

from kam_market_ai.paper_trading.public_routes import dispatch_public_route


def test_public_get_routes_return_minimal_read_only_responses():
    health = dispatch_public_route("GET", "/healthz")
    ready = dispatch_public_route("GET", "/readyz")
    embed = dispatch_public_route("GET", "/embed")
    assert health and loads(health.body) == {"status": "ok", "service": "kam-market-ai", "mode": "read-only"}
    assert ready and loads(ready.body) == {"status": "ready", "source_mode": "offline-demo"}
    assert embed and embed.status_code == 200 and embed.body == "Embed presenter not wired yet."


def test_public_routes_are_get_only_and_have_no_unrelated_capability():
    response = dispatch_public_route("POST", "/healthz")
    assert response and response.status_code == 405 and response.headers == (("Allow", "GET"),)
    assert dispatch_public_route("GET", "/unknown") is None
    source = __import__("kam_market_ai.paper_trading.public_routes", fromlist=["x"]).__file__
    text = open(source, encoding="utf-8").read().lower()
    for forbidden in ("account", "order", "api_key", "websocket", "requests", "urllib", "socket"):
        assert forbidden not in text
