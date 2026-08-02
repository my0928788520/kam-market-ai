from test_dashboard_presenter import model

from kam_market_ai.dashboard.app import DashboardApp
from kam_market_ai.dashboard.presenter import DashboardPresenterConfig, build_dashboard_presenter


def test_invalid_market_view_is_http_200_with_complete_fail_closed_dom(tmp_path):
    presenter = build_dashboard_presenter({}, DashboardPresenterConfig.provisional())
    result = []
    page = b"".join(DashboardApp(tmp_path / "none", presenter=presenter)({"PATH_INFO": "/"}, lambda status, headers: result.append(status))).decode("utf-8")
    assert result == ["200 OK"]
    assert "timeframe-15m" in page and "module-position" in page


def test_invalid_presenter_object_is_internal_error(tmp_path):
    result = []
    body = b"".join(DashboardApp(tmp_path / "none", presenter=object())({"PATH_INFO": "/"}, lambda status, headers: result.append(status)))
    assert result == ["500 Internal Server Error"] and b"Traceback" not in body
