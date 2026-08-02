from test_dashboard_presenter import model

from kam_market_ai.dashboard.presenter import DashboardPresenterConfig, build_dashboard_presenter
from kam_market_ai.dashboard.ui_contract import DashboardUIConfig, render_dashboard_ui


def test_state_classes_are_whitelisted_and_banner_remains_in_dom_when_hidden():
    context = build_dashboard_presenter(model(), DashboardPresenterConfig.provisional()).template_context
    page = render_dashboard_ui(context, DashboardUIConfig.provisional())
    assert 'class="status-banner" hidden' in page
    assert "theme-calm" in page and "state-observing" in page
