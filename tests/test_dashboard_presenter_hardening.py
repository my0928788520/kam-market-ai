from test_dashboard_presenter import model

from kam_market_ai.dashboard.presenter import DashboardPresenterConfig, DashboardThemeState, build_dashboard_presenter
from kam_market_ai.dashboard.serialization import DashboardSerializationConfig, serialize_dashboard_read_model


def test_unknown_state_and_missing_timeframes_fail_closed():
    payload = serialize_dashboard_read_model(model(), DashboardSerializationConfig.provisional())
    payload["display_state"] = "unknown"
    unknown = build_dashboard_presenter(payload, DashboardPresenterConfig.provisional())
    assert not unknown.valid and unknown.theme_state is DashboardThemeState.UNAVAILABLE
    payload = serialize_dashboard_read_model(model(), DashboardSerializationConfig.provisional())
    payload["timeframe_views"] = payload["timeframe_views"][:-1]
    assert not build_dashboard_presenter(payload, DashboardPresenterConfig.provisional()).valid
