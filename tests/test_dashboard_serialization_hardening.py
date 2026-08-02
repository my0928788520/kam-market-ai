import json

from test_dashboard_presenter import model
from kam_market_ai.dashboard.serialization import DashboardSerializationConfig, dashboard_payload_to_canonical_json, serialize_dashboard_read_model


def test_serialization_is_byte_deterministic_and_json_safe():
    config = DashboardSerializationConfig.provisional()
    first = dashboard_payload_to_canonical_json(serialize_dashboard_read_model(model(), config), config)
    second = dashboard_payload_to_canonical_json(serialize_dashboard_read_model(model(), config), config)
    assert first == second and json.loads(first)["serialization_version"] == "1.0"
