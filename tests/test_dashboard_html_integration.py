from test_dashboard_presenter import model

from kam_market_ai.dashboard.app import DashboardApp
from kam_market_ai.dashboard.presenter import DashboardPresenterConfig, build_dashboard_presenter


def test_injected_presenter_renders_v3_html_through_existing_wsgi_app(tmp_path):
    app = DashboardApp(tmp_path / "unused.json", presenter=build_dashboard_presenter(model(), DashboardPresenterConfig.provisional()))
    result, headers = [], []
    body = b"".join(app({"PATH_INFO": "/", "REQUEST_METHOD": "GET"}, lambda status, values: (result.append(status), headers.extend(values)))).decode("utf-8")
    assert result == ["200 OK"]
    assert ("Cache-Control", "no-store") in headers
    assert "id=\"dashboard-three-second-summary\"" in body
    assert "id=\"timeframe-15m\"" in body and "id=\"module-timing\"" in body


def test_existing_wsgi_rejects_non_get_without_changing_legacy_routes(tmp_path):
    result = []
    body = b"".join(DashboardApp(tmp_path / "unused.json")({"PATH_INFO": "/", "REQUEST_METHOD": "POST"}, lambda status, headers: result.append(status)))
    assert result == ["405 Method Not Allowed"] and body == b"Method Not Allowed"
