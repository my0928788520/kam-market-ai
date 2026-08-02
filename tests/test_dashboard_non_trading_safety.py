import re

from test_dashboard_presenter import model
from kam_market_ai.dashboard.presenter import DashboardPresenterConfig, build_dashboard_presenter
from kam_market_ai.dashboard.ui_contract import DashboardUIConfig, render_dashboard_ui


def test_visible_dashboard_text_has_no_transaction_instruction_terms():
    html = render_dashboard_ui(build_dashboard_presenter(model(), DashboardPresenterConfig.provisional()).template_context, DashboardUIConfig.provisional())
    visible = re.sub(r"<[^>]+>", " ", html).lower()
    for token in ("buy", "sell", "long", "short", "enter", "exit", "entry", "stop_loss", "take_profit", "add_position", "reduce_position", "order", "position_size", "leverage"):
        assert not re.search(rf"\b{re.escape(token)}\b", visible)
