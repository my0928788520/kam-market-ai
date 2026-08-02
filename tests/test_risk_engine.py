from __future__ import annotations
from datetime import UTC, datetime
from decimal import Decimal
from kam_market_ai.analysis.position_engine import DataStatus, PositionTimeframe
from kam_market_ai.decision.decision_confidence import DecisionConfidenceConfig, evaluate_decision_confidence
from kam_market_ai.decision.decision_contract import (DECISION_INPUT_CONTRACT_VERSION, DecisionInputContract, DecisionInputStatus, DecisionModuleInput, DecisionModuleType, ModuleConfirmationState, NormalizedModuleState, TimeframeDecisionInput)
from kam_market_ai.decision.risk_engine import RiskEngineConfig, RiskLevel, RiskOperationalState, evaluate_risk
NOW=datetime(2026,8,3,10,tzinfo=UTC)
def contract(status=DecisionInputStatus.READY,timing=NormalizedModuleState.CONFIRMED,mixed=False):
 f={}
 for tf in PositionTimeframe:
  x=lambda m,s:DecisionModuleInput(m,tf,True,True,DataStatus.OK,s,ModuleConfirmationState.CONFIRMED,None,"F","t",NOW,(),None,str(s),"ok")
  f[tf]=TimeframeDecisionInput(tf,x(DecisionModuleType.POSITION,NormalizedModuleState.BULLISH),x(DecisionModuleType.TREND,NormalizedModuleState.BEARISH if mixed else NormalizedModuleState.BULLISH),x(DecisionModuleType.STRUCTURE,NormalizedModuleState.BULLISH),x(DecisionModuleType.TIMING,timing),status,True,True,NOW,(),())
 return DecisionInputContract(DECISION_INPUT_CONTRACT_VERSION,NOW,NOW,f,status,4,4,(),(),{})
def test_valid_waiting_conflict_and_invalid_risk():
 cfg=RiskEngineConfig.provisional(); c=contract(); r=evaluate_risk(c,evaluate_decision_confidence(c,DecisionConfidenceConfig.provisional()),cfg); assert r.operational_state is RiskOperationalState.VALID
 c=contract(timing=NormalizedModuleState.WAITING); r=evaluate_risk(c,evaluate_decision_confidence(c,DecisionConfidenceConfig.provisional()),cfg); assert r.overall_risk_score>=Decimal("30") and r.operational_state is RiskOperationalState.PROVISIONAL
 c=contract(mixed=True); r=evaluate_risk(c,evaluate_decision_confidence(c,DecisionConfidenceConfig.provisional()),cfg); assert r.overall_risk_score>=Decimal("50")
 c=contract(status=DecisionInputStatus.INVALID); r=evaluate_risk(c,evaluate_decision_confidence(c,DecisionConfidenceConfig.provisional()),cfg); assert r.overall_risk_level is RiskLevel.INVALID
def test_source_mismatch_and_config_validation():
 c=contract(); confidence=evaluate_decision_confidence(c,DecisionConfidenceConfig.provisional()); bad=DecisionInputContract(c.contract_version,NOW,NOW.replace(minute=1),c.timeframes,c.overall_status,4,4,(),(),{})
 assert evaluate_risk(bad,confidence,RiskEngineConfig.provisional()).operational_state is RiskOperationalState.INVALID
 try: RiskEngineConfig(category_weights={})
 except ValueError: pass
 else: assert False
