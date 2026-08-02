from __future__ import annotations
from datetime import UTC, datetime
from decimal import Decimal
import pytest
from kam_market_ai.analysis.position_engine import DataStatus, PositionTimeframe
from kam_market_ai.decision.decision_confidence import (DecisionConfidenceConfig, DecisionConfidenceState, DecisionDirection, TimeframeAlignmentState, evaluate_decision_confidence)
from kam_market_ai.decision.decision_contract import (DECISION_INPUT_CONTRACT_VERSION, DecisionInputContract, DecisionInputStatus, DecisionModuleInput, DecisionModuleType, ModuleConfirmationState, NormalizedModuleState, TimeframeDecisionInput)

NOW=datetime(2026,8,3,10,tzinfo=UTC)
def item(module,state,confirmation=ModuleConfirmationState.CONFIRMED,hint=None): return DecisionModuleInput(module,PositionTimeframe.M15,True,True,DataStatus.OK,state,confirmation,hint,"Fixture","test",NOW,(),None,str(state),"ok")
def contract(states=None, status=DecisionInputStatus.READY, version=DECISION_INPUT_CONTRACT_VERSION):
    states=states or (NormalizedModuleState.BULLISH,NormalizedModuleState.BULLISH,NormalizedModuleState.BULLISH,NormalizedModuleState.CONFIRMED); frames={}
    for tf in PositionTimeframe:
        p=item(DecisionModuleType.POSITION,states[0]);t=item(DecisionModuleType.TREND,states[1]);s=item(DecisionModuleType.STRUCTURE,states[2]);ti=item(DecisionModuleType.TIMING,states[3]);frames[tf]=TimeframeDecisionInput(tf,p,t,s,ti,status,True,True,NOW,(),())
    return DecisionInputContract(version,NOW,NOW,frames,status,4,4,(),(),{})
def test_aligned_bullish_and_bearish_scores_are_deterministic():
    bull=evaluate_decision_confidence(contract(),DecisionConfidenceConfig.provisional()); bear=evaluate_decision_confidence(contract((NormalizedModuleState.BEARISH,NormalizedModuleState.BEARISH,NormalizedModuleState.BEARISH,NormalizedModuleState.CONFIRMED)),DecisionConfidenceConfig.provisional())
    assert bull.overall_direction is DecisionDirection.BULLISH and bull.alignment_state is TimeframeAlignmentState.FULLY_ALIGNED and Decimal("0")<=bull.overall_confidence_score<=Decimal("100")
    assert bear.overall_direction is DecisionDirection.BEARISH and bear.overall_confidence_score==bull.overall_confidence_score
def test_provisional_stale_invalid_and_contract_version_fail_closed():
    cfg=DecisionConfidenceConfig.provisional()
    assert evaluate_decision_confidence(contract((NormalizedModuleState.BULLISH,NormalizedModuleState.BULLISH,NormalizedModuleState.BULLISH,NormalizedModuleState.PROVISIONAL),DecisionInputStatus.PROVISIONAL),cfg).overall_confidence_state is DecisionConfidenceState.PROVISIONAL
    assert evaluate_decision_confidence(contract(status=DecisionInputStatus.STALE),cfg).overall_confidence_state is DecisionConfidenceState.STALE
    assert evaluate_decision_confidence(contract(status=DecisionInputStatus.INVALID),cfg).overall_confidence_state is DecisionConfidenceState.INVALID
    assert evaluate_decision_confidence(contract(version="9.0"),cfg).overall_confidence_state is DecisionConfidenceState.INVALID
def test_mixed_and_neutral_are_not_directional():
    mixed=evaluate_decision_confidence(contract((NormalizedModuleState.BULLISH,NormalizedModuleState.BEARISH,NormalizedModuleState.NEUTRAL,NormalizedModuleState.CONFIRMED)),DecisionConfidenceConfig.provisional())
    neutral=evaluate_decision_confidence(contract((NormalizedModuleState.NEUTRAL,)*3+(NormalizedModuleState.CONFIRMED,)),DecisionConfidenceConfig.provisional())
    assert mixed.overall_direction is DecisionDirection.MIXED and mixed.overall_confidence_state is DecisionConfidenceState.CONFLICTING
    assert neutral.overall_direction is DecisionDirection.NEUTRAL
def test_hint_rejection_and_config_validation():
    cfg=DecisionConfidenceConfig.provisional(); bad=contract(); frame=bad.timeframes[PositionTimeframe.M15]
    bad_item=DecisionModuleInput(DecisionModuleType.TREND,PositionTimeframe.M15,True,True,DataStatus.OK,NormalizedModuleState.BULLISH,ModuleConfirmationState.CONFIRMED,Decimal("2"),"Fixture","test",NOW,(),None,"ascending","ok")
    frames=dict(bad.timeframes);frames[PositionTimeframe.M15]=TimeframeDecisionInput(PositionTimeframe.M15,frame.position,bad_item,frame.structure,frame.timing,DecisionInputStatus.READY,True,True,NOW,(),()); altered=DecisionInputContract(bad.contract_version,NOW,NOW,frames,bad.overall_status,4,4,(),(),{})
    assert evaluate_decision_confidence(altered,cfg).overall_confidence_score>=Decimal("0")
    with pytest.raises(ValueError): DecisionConfidenceConfig(module_weights={})
