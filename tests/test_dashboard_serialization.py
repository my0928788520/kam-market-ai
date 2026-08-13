import json
from test_risk_engine import contract
from kam_market_ai.decision.decision_confidence import DecisionConfidenceConfig,evaluate_decision_confidence
from kam_market_ai.decision.risk_engine import RiskEngineConfig,evaluate_risk
from kam_market_ai.decision.next_step_engine import NextStepEngineConfig,evaluate_next_step
from kam_market_ai.dashboard.read_model import DashboardReadModelConfig,build_dashboard_read_model
from kam_market_ai.dashboard.serialization import DashboardSerializationConfig,dashboard_payload_to_canonical_json,serialize_dashboard_read_model
def test_serialization_is_json_safe_and_timeframe_ordered():
 c=contract();co=evaluate_decision_confidence(c,DecisionConfidenceConfig.provisional());r=evaluate_risk(c,co,RiskEngineConfig.provisional());n=evaluate_next_step(c,co,r,NextStepEngineConfig.provisional());m=build_dashboard_read_model(c,co,r,n,DashboardReadModelConfig.provisional());cfg=DashboardSerializationConfig.provisional();p=serialize_dashboard_read_model(m,cfg);a=dashboard_payload_to_canonical_json(p,cfg);assert json.loads(a)==p and [x["timeframe"] for x in p["timeframe_views"]]==["5m","15m","60m","1d","1w"]
