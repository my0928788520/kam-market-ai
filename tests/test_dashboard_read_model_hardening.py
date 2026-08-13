from test_dashboard_presenter import model

from kam_market_ai.dashboard.read_model import DashboardDisplayState


def test_read_model_is_deterministic_and_has_fixed_timeframes():
    first, second = model(), model()
    assert first == second
    assert first.display_state is DashboardDisplayState.OBSERVING
    assert [frame.value for frame in first.timeframes] == ["5m", "15m", "60m", "1d", "1w"]
