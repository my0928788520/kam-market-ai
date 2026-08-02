from test_dashboard_presenter import model

from kam_market_ai.dashboard.presenter import DashboardPresenterConfig, build_dashboard_presenter
from kam_market_ai.dashboard.serialization import DashboardSerializationConfig, serialize_dashboard_read_model


def test_serialized_payload_and_read_model_produce_the_same_core_view():
    read_model = model()
    payload = serialize_dashboard_read_model(read_model, DashboardSerializationConfig.provisional())
    direct = build_dashboard_presenter(read_model, DashboardPresenterConfig.provisional())
    serialized = build_dashboard_presenter(payload, DashboardPresenterConfig.provisional())
    assert serialized.valid == direct.valid
    assert serialized.display_state == direct.display_state
    assert serialized.timeframe_cards == direct.timeframe_cards
    assert serialized.market_decision["risk_score_text"] == direct.market_decision["risk_score_text"]
