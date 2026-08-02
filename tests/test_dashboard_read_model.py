from test_risk_engine import contract
from kam_market_ai.decision.decision_confidence import DecisionConfidenceConfig,evaluate_decision_confidence
from kam_market_ai.decision.risk_engine import RiskEngineConfig,evaluate_risk
from kam_market_ai.decision.next_step_engine import NextStepEngineConfig,evaluate_next_step
from kam_market_ai.dashboard.read_model import DashboardDisplayState,DashboardReadModelConfig,build_dashboard_read_model
def test_read_model_observing_and_source_mismatch():
 c=contract();co=evaluate_decision_confidence(c,DecisionConfidenceConfig.provisional());r=evaluate_risk(c,co,RiskEngineConfig.provisional());n=evaluate_next_step(c,co,r,NextStepEngineConfig.provisional());m=build_dashboard_read_model(c,co,r,n,DashboardReadModelConfig.provisional());assert m.display_state is DashboardDisplayState.OBSERVING and set(m.timeframes)==set(c.timeframes)
 bad=build_dashboard_read_model(c,co,r,n.__class__(n.engine_version,n.contract_version,n.confidence_engine_version,n.risk_engine_version,n.evaluated_at.replace(minute=1),n.next_step,n.operational_state,n.priority,n.reason_codes,n.timeframe_steps,n.reassessment_triggers,n.review_modules,n.supporting_factors,n.valid,n.warnings,n.error_codes),DashboardReadModelConfig.provisional());assert bad.display_state is DashboardDisplayState.INVALID
