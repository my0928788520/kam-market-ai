from __future__ import annotations
import pytest
from test_risk_engine import contract
from kam_market_ai.decision.decision_confidence import DecisionConfidenceConfig, evaluate_decision_confidence
from kam_market_ai.decision.next_step_engine import NextStepEngineConfig, NextStepOperationalState, NextStepType, evaluate_next_step
from kam_market_ai.decision.risk_engine import RiskEngineConfig, evaluate_risk
from kam_market_ai.decision.decision_contract import DecisionInputStatus, NormalizedModuleState
def result(c):
 confidence=evaluate_decision_confidence(c,DecisionConfidenceConfig.provisional());risk=evaluate_risk(c,confidence,RiskEngineConfig.provisional());return evaluate_next_step(c,confidence,risk,NextStepEngineConfig.provisional())
def test_observe_wait_and_invalid():
 assert result(contract()).next_step is NextStepType.MAINTAIN_OBSERVATION
 assert result(contract(timing=NormalizedModuleState.WAITING)).next_step is NextStepType.WAIT_FOR_CANDLE_CLOSE
 assert result(contract(status=DecisionInputStatus.INVALID)).operational_state is NextStepOperationalState.INVALID
def test_config_validation():
 with pytest.raises(ValueError): NextStepEngineConfig(supported_contract_versions=frozenset())
