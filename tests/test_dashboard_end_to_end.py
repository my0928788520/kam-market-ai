from test_dashboard_presenter import model

from kam_market_ai.dashboard.presenter import DashboardPresenterConfig, build_dashboard_presenter
from kam_market_ai.dashboard.serialization import DashboardSerializationConfig, serialize_dashboard_read_model
from kam_market_ai.dashboard.ui_contract import DashboardUIConfig, render_dashboard_ui
from kam_market_ai.dashboard.wsgi_adapter import DashboardWSGIAdapterConfig, build_dashboard_wsgi_context


def test_read_model_to_serialization_to_presenter_to_wsgi_to_html():
    payload = serialize_dashboard_read_model(model(), DashboardSerializationConfig.provisional())
    presenter = build_dashboard_presenter(payload, DashboardPresenterConfig.provisional())
    response = build_dashboard_wsgi_context(presenter, DashboardWSGIAdapterConfig.provisional())
    page = render_dashboard_ui(response["template_context"], DashboardUIConfig.provisional())
    assert response["http_status"] == 200 and "Cache-Control" in str(response["headers"])
    assert "dashboard-three-second-summary" in page and page.count("timeframe-") >= 4
