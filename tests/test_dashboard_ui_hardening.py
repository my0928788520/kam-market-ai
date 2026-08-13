from test_dashboard_presenter import model

from kam_market_ai.dashboard.presenter import DashboardPresenterConfig, build_dashboard_presenter
from kam_market_ai.dashboard.ui_contract import DashboardUIConfig, render_dashboard_ui


def test_ui_has_one_h1_and_four_fixed_timeframes_and_modules():
    page = render_dashboard_ui(build_dashboard_presenter(model(), DashboardPresenterConfig.provisional()).template_context, DashboardUIConfig.provisional())
    assert page.count("<h1>") == 1
    assert all(f'id="timeframe-{value}"' in page for value in ("5m", "15m", "60m", "1d", "1w"))
    assert all(f'id="module-{value}"' in page for value in ("position", "trend", "structure", "timing"))
