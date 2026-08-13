from test_risk_engine import contract

from kam_market_ai.dashboard.presenter import DashboardPresenterConfig, DashboardThemeState, build_dashboard_presenter
from kam_market_ai.dashboard.read_model import DashboardReadModelConfig, build_dashboard_read_model
from kam_market_ai.decision.decision_confidence import DecisionConfidenceConfig, evaluate_decision_confidence
from kam_market_ai.decision.next_step_engine import NextStepEngineConfig, evaluate_next_step
from kam_market_ai.decision.risk_engine import RiskEngineConfig, evaluate_risk


def model():
    source = contract()
    confidence = evaluate_decision_confidence(source, DecisionConfidenceConfig.provisional())
    risk = evaluate_risk(source, confidence, RiskEngineConfig.provisional())
    next_step = evaluate_next_step(source, confidence, risk, NextStepEngineConfig.provisional())
    return build_dashboard_read_model(source, confidence, risk, next_step, DashboardReadModelConfig.provisional())


def test_presenter_builds_fixed_order_safe_template_context():
    view = build_dashboard_presenter(model(), DashboardPresenterConfig.provisional())
    assert view.presenter_version == "1.0"
    assert view.page_title == "KAM Trade V3"
    assert view.page_subtitle == "Trading Decision Operating System"
    assert view.theme_state is DashboardThemeState.CALM
    assert [card["timeframe"] for card in view.timeframe_cards] == ["5m", "15m", "60m", "1d", "1w"]
    assert len(view.module_sections) == 20
    assert view.template_context["accessibility"]["language"] == "zh-TW"
    assert view.template_context["header"]["badge_class"].startswith("state-")


def test_presenter_fails_closed_and_escapes_untrusted_text():
    view = build_dashboard_presenter({"serialization_version": "999", "read_model_version": "999"}, DashboardPresenterConfig.provisional())
    assert not view.valid and view.display_state == "invalid" and view.theme_state is DashboardThemeState.UNAVAILABLE
    payload = {"serialization_version": "1.0", "read_model_version": "1.0", "warnings": ["<script>alert(1)</script>"]}
    invalid = build_dashboard_presenter(payload, DashboardPresenterConfig.provisional())
    assert "<script>" not in str(invalid.template_context)
