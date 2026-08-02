from test_dashboard_presenter import model

from kam_market_ai.dashboard.presenter import DashboardPresenterConfig, build_dashboard_presenter


def test_accessibility_contract_and_display_output_are_non_transactional():
    view = build_dashboard_presenter(model(), DashboardPresenterConfig.provisional())
    accessibility = view.accessibility
    assert accessibility["language"] == "zh-TW"
    assert accessibility["heading_order_valid"] is True
    assert all(card["aria_label"] for card in view.timeframe_cards)
    def text_values(value):
        if isinstance(value, dict):
            return " ".join(text_values(item) for item in value.values())
        if isinstance(value, (tuple, list)):
            return " ".join(text_values(item) for item in value)
        return str(value)
    rendered_values = text_values(view.template_context).lower()
    for token in ("buy", "sell", "long", "short", "stop_loss", "take_profit", "add_position", "reduce_position"):
        assert token not in rendered_values
