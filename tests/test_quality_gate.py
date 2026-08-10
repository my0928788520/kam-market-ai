from decimal import Decimal

from test_risk_engine import contract

from kam_market_ai.decision.decision_confidence import (
    DecisionConfidenceConfig,
    evaluate_decision_confidence,
)
from kam_market_ai.decision.quality_gate import (
    MarketRegime,
    QualityContext,
    QualityDecision,
    QualityGateConfig,
    QualityReason,
    evaluate_quality_gate,
)
from kam_market_ai.decision.risk_engine import RiskEngineConfig, evaluate_risk


def evaluation(context=None):
    source = contract()
    confidence = evaluate_decision_confidence(source, DecisionConfidenceConfig.provisional())
    risk = evaluate_risk(source, confidence, RiskEngineConfig.provisional())
    context = context or QualityContext(MarketRegime.TREND, Decimal(80), Decimal(2), Decimal(1), True)
    return evaluate_quality_gate(confidence, risk, context, QualityGateConfig(minimum_confidence=Decimal(60)))


def test_all_quality_conditions_create_shadow_a_grade_only():
    result = evaluation()
    assert result.decision is QualityDecision.A_GRADE
    assert result.score == Decimal("100.00")
    assert result.passed_conditions == result.total_conditions == 7
    assert result.live_order_allowed is False


def test_regime_data_and_behavior_rules_fail_closed():
    blocked = evaluation(QualityContext(MarketRegime.RANGE, Decimal(80), Decimal(2), Decimal(1), True))
    assert blocked.decision is QualityDecision.BLOCK
    assert QualityReason.REGIME_BLOCKED in blocked.blockers
    cooldown = evaluation(QualityContext(MarketRegime.TREND, Decimal(80), Decimal(2), Decimal(1), True, consecutive_losses=2))
    assert cooldown.decision is QualityDecision.BLOCK
    assert QualityReason.COOLDOWN_ACTIVE in cooldown.blockers


def test_incomplete_noncritical_advantage_waits_and_config_validates():
    waiting = evaluation(QualityContext(MarketRegime.TREND, Decimal(60), Decimal(2), Decimal(1), True))
    assert waiting.decision is QualityDecision.WAIT
    assert QualityReason.LOCATION_POOR in waiting.blockers
    try:
        QualityGateConfig(minimum_volatility_ratio=Decimal(2), maximum_volatility_ratio=Decimal(1))
    except ValueError:
        pass
    else:
        assert False
