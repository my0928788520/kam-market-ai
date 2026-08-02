from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from kam_market_ai.analysis.position_engine import DataStatus, PositionRangeResult, PositionTimeframe, RangeState
from kam_market_ai.analysis.structure_engine import PatternResult, PatternState, PatternType, SequenceState, StructureBias, StructureResult, SwingLabel
from kam_market_ai.analysis.timing_engine import CandleTimingState, FreshnessState, MarketPhase, SessionType, TimingReadiness, TimingResult
from kam_market_ai.analysis.trend_engine import RelationToTrendline, TrendState, TrendlineResult, TrendlineType
from kam_market_ai.decision.decision_contract import (DECISION_INPUT_CONTRACT_VERSION, DecisionInputConfig, DecisionInputStatus, ModuleConfirmationState, NormalizedModuleState, build_decision_input_contract, normalize_position_result, normalize_structure_result, normalize_timing_result, normalize_trend_result)

NOW=datetime(2026,8,3,10,tzinfo=UTC); TF=PositionTimeframe.M15
def position(state=RangeState.MIDDLE,status=DataStatus.OK): return PositionRangeResult(TF,Decimal("110"),Decimal("90"),Decimal("20"),Decimal("100"),Decimal("50"),Decimal("10"),Decimal("10"),state,status,10,10,NOW,())
def trend(kind=TrendlineType.NONE,state=TrendState.NO_VALID_TRENDLINE,status=DataStatus.OK): return TrendlineResult(TF,kind,None,None,None,None,Decimal("100"),None,None,RelationToTrendline.INSUFFICIENT_DATA,0,0,None,None,True,Decimal("0.5"),state,status,10,10,NOW,())
def pattern(kind=PatternType.NONE,state=PatternState.NONE): return PatternResult(kind,state,None,None,None,None,None,None,None,None,None,None,None,0,None,state not in {PatternState.NONE,PatternState.INVALID},Decimal("0.5"),())
def structure(seq=SequenceState.RANGE_LIKE,w=None,m=None,status=DataStatus.OK):
    return StructureResult(TF,(),(),SwingLabel.UNCLASSIFIED,SwingLabel.UNCLASSIFIED,seq,StructureBias.NEUTRAL,PatternType.NONE,w or pattern(),m or pattern(),None,Decimal("100"),NOW,10,5,status,False,True,())
def timing(readiness=TimingReadiness.CONFIRMED,status=DataStatus.OK):
    return TimingResult(TF,NOW,"Asia/Taipei",NOW.date(),NOW.date(),SessionType.DAY,MarketPhase.REGULAR,None,None,1,1,CandleTimingState.CLOSED,None,None,None,None,0,True,False,True,FreshnessState.FRESH,NOW,0,readiness,status,True,())

@pytest.mark.parametrize(("state","expected"),[(RangeState.NEAR_HIGH,NormalizedModuleState.BULLISH),(RangeState.NEAR_LOW,NormalizedModuleState.BEARISH),(RangeState.BREAKOUT_UP,NormalizedModuleState.SUPPORTIVE),(RangeState.MIDDLE,NormalizedModuleState.NEUTRAL)])
def test_position_mapping(state,expected): assert normalize_position_result(position(state),TF).normalized_state is expected
@pytest.mark.parametrize(("kind","expected"),[(TrendlineType.ASCENDING,NormalizedModuleState.BULLISH),(TrendlineType.DESCENDING,NormalizedModuleState.BEARISH),(TrendlineType.NONE,NormalizedModuleState.NEUTRAL)])
def test_trend_mapping(kind,expected): assert normalize_trend_result(trend(kind),TF).normalized_state is expected
def test_structure_mapping_confirmation_and_provisional():
    assert normalize_structure_result(structure(SequenceState.BULLISH_CONTINUATION),TF).normalized_state is NormalizedModuleState.BULLISH
    candidate=normalize_structure_result(structure(w=pattern(PatternType.W_BOTTOM,PatternState.CANDIDATE)),TF)
    assert candidate.normalized_state is NormalizedModuleState.PROVISIONAL and candidate.confirmation_state is ModuleConfirmationState.PROVISIONAL
def test_timing_mapping():
    assert normalize_timing_result(timing(TimingReadiness.CONFIRMED),TF,DecisionInputConfig.provisional()).normalized_state is NormalizedModuleState.CONFIRMED
    assert normalize_timing_result(timing(TimingReadiness.WAIT_FOR_CLOSE),TF,DecisionInputConfig.provisional()).normalized_state is NormalizedModuleState.WAITING
def test_ready_contract_and_raw_traceability():
    maps={TF:position()},{TF:trend()},{TF:structure()},{TF:timing()}
    contract=build_decision_input_contract(*maps,NOW,DecisionInputConfig(required_timeframes=(TF,)))
    frame=contract.timeframes[TF]
    assert contract.contract_version==DECISION_INPUT_CONTRACT_VERSION and frame.input_status is DecisionInputStatus.READY and frame.position.raw_state=="middle"
def test_partial_stale_ambiguous_invalid_and_error_precedence():
    cfg=DecisionInputConfig(required_timeframes=(TF,))
    assert build_decision_input_contract({TF:position()},{},{TF:structure()},{TF:timing()},NOW,cfg).overall_status is DecisionInputStatus.UNAVAILABLE
    assert build_decision_input_contract({TF:position(status=DataStatus.STALE)},{TF:trend()},{TF:structure()},{TF:timing()},NOW,cfg).overall_status is DecisionInputStatus.STALE
    assert build_decision_input_contract({TF:position()},{TF:trend(TrendlineType.AMBIGUOUS,TrendState.AMBIGUOUS)},{TF:structure()},{TF:timing()},NOW,cfg).overall_status is DecisionInputStatus.AMBIGUOUS
    assert build_decision_input_contract({TF:position(status=DataStatus.INVALID)},{TF:trend()},{TF:structure()},{TF:timing()},NOW,cfg).overall_status is DecisionInputStatus.INVALID
def test_mismatch_type_version_and_timezone_fail_closed():
    cfg=DecisionInputConfig(required_timeframes=(TF,))
    bad=build_decision_input_contract({TF:object()},{TF:trend()},{TF:structure()},{TF:timing()},NOW,cfg)
    assert bad.timeframes[TF].position.error_code=="invalid_position_result_type"
    with pytest.raises(ValueError): build_decision_input_contract({}, {}, {}, {}, NOW.replace(tzinfo=None),cfg)
    with pytest.raises(ValueError): build_decision_input_contract({}, {}, {}, {}, NOW,cfg,"2.0")
def test_config_validation():
    with pytest.raises(ValueError): DecisionInputConfig(required_timeframes=())
