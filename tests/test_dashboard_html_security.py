from test_dashboard_presenter import model
import re

from kam_market_ai.dashboard.presenter import DashboardPresenterConfig, build_dashboard_presenter
from kam_market_ai.dashboard.serialization import DashboardSerializationConfig, serialize_dashboard_read_model
from kam_market_ai.dashboard.ui_contract import DashboardUIConfig, render_dashboard_ui


def test_presenter_escaped_content_cannot_become_html_or_event_attributes():
    payload = serialize_dashboard_read_model(model(), DashboardSerializationConfig.provisional())
    payload["warnings"] = ["<script>alert(1)</script><img src=x onerror=alert(1)>\" onmouseover=\"alert(1)"]
    page = render_dashboard_ui(build_dashboard_presenter(payload, DashboardPresenterConfig.provisional()).template_context, DashboardUIConfig.provisional())
    assert "<script>" not in page and "<img src=x" not in page and "onmouseover=\"alert(1)" not in page


def test_visible_output_has_no_transaction_instruction_terms():
    page = render_dashboard_ui(build_dashboard_presenter(model(), DashboardPresenterConfig.provisional()).template_context, DashboardUIConfig.provisional()).lower()
    visible = re.sub(r"<[^>]+>", " ", page)
    for token in ("buy", "sell", "long", "short", "enter", "exit", "entry", "stop_loss", "take_profit", "add_position", "reduce_position"):
        assert not re.search(rf"\b{re.escape(token)}\b", visible)
