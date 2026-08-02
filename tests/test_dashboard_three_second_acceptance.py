from test_dashboard_presenter import model

from kam_market_ai.dashboard.presenter import DashboardPresenterConfig, build_dashboard_presenter
from kam_market_ai.dashboard.ui_contract import DashboardUIConfig, render_dashboard_ui


def test_above_fold_summary_repeats_only_the_four_primary_decision_values():
    view = build_dashboard_presenter(model(), DashboardPresenterConfig.provisional())
    page = render_dashboard_ui(view.template_context, DashboardUIConfig.provisional())
    summary = page.split('id="dashboard-three-second-summary"', 1)[1].split('id="dashboard-market-decision"', 1)[0]
    for value in (view.three_second_summary["direction_text"], view.three_second_summary["confidence_text"], view.three_second_summary["risk_text"], view.three_second_summary["next_step_text"]):
        assert str(value) in summary
    assert "raw_state" not in summary and "source_version" not in summary
