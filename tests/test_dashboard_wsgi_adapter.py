from pathlib import Path

import pytest

from test_dashboard_presenter import model
from kam_market_ai.dashboard.presenter import DashboardPresenterConfig, build_dashboard_presenter
from kam_market_ai.dashboard.wsgi_adapter import DashboardWSGIAdapterConfig, build_dashboard_wsgi_context, load_fixture_preview


def test_wsgi_context_keeps_market_invalid_pages_as_http_200_and_no_store():
    config = DashboardWSGIAdapterConfig.provisional()
    context = build_dashboard_wsgi_context(build_dashboard_presenter(model(), DashboardPresenterConfig.provisional()), config)
    assert context["http_status"] == 200
    assert ("Content-Type", "text/html; charset=utf-8") in context["headers"]
    assert ("Cache-Control", "no-store") in context["headers"]
    invalid = build_dashboard_presenter({}, DashboardPresenterConfig.provisional())
    assert build_dashboard_wsgi_context(invalid, config)["http_status"] == 200


def test_fixture_preview_is_explicitly_development_only_and_has_no_path_traversal():
    config = DashboardWSGIAdapterConfig(allow_fixture_preview=True, development_mode=True)
    directory = Path(__file__).parent / "fixtures" / "dashboard"
    assert load_fixture_preview("stale", directory, config)["scenario"] == "stale"
    with pytest.raises(ValueError):
        load_fixture_preview("../stale", directory, config)
    with pytest.raises(PermissionError):
        load_fixture_preview("stale", directory, DashboardWSGIAdapterConfig.provisional())
