from __future__ import annotations
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
import pytest
from kam_market_ai.analysis.pivot_detector import Pivot, PivotType
from kam_market_ai.analysis.position_engine import DataStatus, PositionTimeframe
from kam_market_ai.analysis.structure_engine import (NecklineRelation, PatternState, PatternType, SequenceState, StructureBias, StructureDuplicatePolicy, StructureEngineConfig, StructureToleranceMode, SwingLabel, evaluate_all_structures, evaluate_structure)
from kam_market_ai.models import Candle, Instrument

NOW=datetime(2026,7,31,10,tzinfo=UTC)
def candles(closes: list[float]|None=None)->list[Candle]:
    closes=closes or [105]*10
    return [Candle(Instrument.MTX,NOW-timedelta(minutes=11-i),NOW-timedelta(minutes=10-i),105,120,90,close,1) for i,close in enumerate(closes)]
def cfg(**x:object)->StructureEngineConfig:
    m={t:20 for t in PositionTimeframe}; n={t:3 for t in PositionTimeframe}; d={t:Decimal("2") for t in PositionTimeframe}; h={t:Decimal("0.1") for t in PositionTimeframe}; i={t:2 for t in PositionTimeframe}; mx={t:10 for t in PositionTimeframe}; age={t:20 for t in PositionTimeframe}; stale={t:timedelta(days=2) for t in PositionTimeframe}
    return StructureEngineConfig(x.get("lookback_by_timeframe",m),x.get("minimum_closed_candles_by_timeframe",n),x.get("minimum_pivots_by_timeframe",n),x.get("swing_comparison_tolerance_by_timeframe",d),x.get("pattern_similarity_tolerance_by_timeframe",d),x.get("neckline_tolerance_by_timeframe",{t:Decimal("0.5") for t in PositionTimeframe}),x.get("invalidation_tolerance_by_timeframe",d),x.get("minimum_pattern_height_by_timeframe",h),x.get("minimum_leg_separation_bars_by_timeframe",i),x.get("maximum_leg_separation_bars_by_timeframe",mx),x.get("confirmation_bars_by_timeframe",{t:2 for t in PositionTimeframe}),x.get("maximum_candidate_age_bars_by_timeframe",age),x.get("stale_after_by_timeframe",stale),swing_comparison_tolerance_mode=StructureToleranceMode.FIXED_POINTS,pattern_similarity_tolerance_mode=StructureToleranceMode.FIXED_POINTS,neckline_tolerance_mode=StructureToleranceMode.FIXED_POINTS,invalidation_tolerance_mode=StructureToleranceMode.FIXED_POINTS,allow_sort_input=x.get("allow_sort_input",True),duplicate_timestamp_policy=x.get("duplicate_timestamp_policy",StructureDuplicatePolicy.REJECT),ambiguity_score_gap=x.get("ambiguity_score_gap",Decimal("0.01")))
def pivot(kind:PivotType,index:int,price:int,tf:PositionTimeframe=PositionTimeframe.M15)->Pivot:
    c=candles()[index]; return Pivot(kind,tf,index,c.end,Decimal(str(price)),1,1,True,c.end)
def with_prices(data:list[Candle], points: list[Pivot])->list[Candle]:
    out=data[:]
    for p in points:
        c=out[p.candle_index]; out[p.candle_index]=replace(c,high=float(p.price) if p.pivot_type is PivotType.HIGH else c.high,low=float(p.price) if p.pivot_type is PivotType.LOW else c.low,open=max(float(p.price),c.low),close=max(float(p.price),c.low))
    return out
def evaluate(points:list[Pivot],price:float=105,cs:list[Candle]|None=None,**x:object):
    cs=with_prices(cs or candles(),points); return evaluate_structure(PositionTimeframe.M15,cs,price,NOW,cfg(**x),points)

def test_swing_labels_and_independent_high_low_chains() -> None:
    ps=[pivot(PivotType.HIGH,1,110),pivot(PivotType.LOW,2,100),pivot(PivotType.HIGH,3,115),pivot(PivotType.LOW,4,105)]
    result=evaluate(ps)
    assert [x.swing_label for x in result.swing_points]==[SwingLabel.UNCLASSIFIED,SwingLabel.UNCLASSIFIED,SwingLabel.HH,SwingLabel.HL]
    assert result.sequence_state is SequenceState.BULLISH_CONTINUATION and result.structure_bias is StructureBias.BULLISH

def test_lh_ll_equal_and_insufficient_sequences() -> None:
    bear=[pivot(PivotType.HIGH,1,115),pivot(PivotType.LOW,2,105),pivot(PivotType.HIGH,3,110),pivot(PivotType.LOW,4,100)]
    equal=[pivot(PivotType.HIGH,1,110),pivot(PivotType.LOW,2,100),pivot(PivotType.HIGH,3,111),pivot(PivotType.LOW,4,101)]
    assert evaluate(bear).sequence_state is SequenceState.BEARISH_CONTINUATION
    assert [x.swing_label for x in evaluate(equal).swing_points][-2:]==[SwingLabel.EQH,SwingLabel.EQL]
    assert evaluate([pivot(PivotType.LOW,2,100)]).data_status is DataStatus.INSUFFICIENT_DATA

def test_w_bottom_candidate_testing_confirmation_and_failure() -> None:
    ps=[pivot(PivotType.LOW,2,100),pivot(PivotType.HIGH,4,110),pivot(PivotType.LOW,6,101)]
    candidate=evaluate(ps,105); testing=evaluate(ps,110)
    confirmed=evaluate(ps,112,cs=candles([105,105,100,105,110,105,101,111,112,112]))
    failed=evaluate([pivot(PivotType.LOW,2,100),pivot(PivotType.HIGH,4,110),pivot(PivotType.LOW,6,97)],105)
    assert candidate.w_bottom.state is PatternState.CANDIDATE
    assert testing.w_bottom.state is PatternState.NECKLINE_TESTING
    assert confirmed.w_bottom.state is PatternState.CONFIRMED and confirmed.w_bottom.current_relation_to_neckline is NecklineRelation.BREAKOUT_UP
    assert failed.w_bottom.state is PatternState.FAILED

def test_m_top_candidate_confirmation_and_failure() -> None:
    ps=[pivot(PivotType.HIGH,2,110),pivot(PivotType.LOW,4,100),pivot(PivotType.HIGH,6,109)]
    confirmed=evaluate(ps,98,cs=candles([105,105,110,105,100,105,109,99,98,98]))
    failed=evaluate([pivot(PivotType.HIGH,2,110),pivot(PivotType.LOW,4,100),pivot(PivotType.HIGH,6,113)],105)
    assert confirmed.m_top.state is PatternState.CONFIRMED and confirmed.m_top.current_relation_to_neckline is NecklineRelation.BREAKDOWN_DOWN
    assert failed.m_top.state is PatternState.FAILED

def test_pattern_leg_height_age_and_ambiguity_fail_closed() -> None:
    short=[pivot(PivotType.LOW,2,100),pivot(PivotType.HIGH,3,110),pivot(PivotType.LOW,4,100)]
    flat=[pivot(PivotType.LOW,2,100),pivot(PivotType.HIGH,4,100.05),pivot(PivotType.LOW,6,100)]
    old=[pivot(PivotType.LOW,1,100),pivot(PivotType.HIGH,3,110),pivot(PivotType.LOW,5,100)]
    assert evaluate(short,minimum_leg_separation_bars_by_timeframe={t:3 for t in PositionTimeframe}).w_bottom.state is PatternState.NONE
    assert evaluate(flat).w_bottom.state is PatternState.NONE
    assert evaluate(old,maximum_candidate_age_bars_by_timeframe={t:2 for t in PositionTimeframe}).w_bottom.state is PatternState.FAILED
    many=[pivot(PivotType.LOW,1,100),pivot(PivotType.HIGH,3,110),pivot(PivotType.LOW,5,100),pivot(PivotType.HIGH,6,110),pivot(PivotType.LOW,8,100)]
    assert evaluate(many,ambiguity_score_gap=Decimal("999")).active_pattern_type is PatternType.AMBIGUOUS

def test_precomputed_pivot_validation_and_data_errors() -> None:
    ps=[pivot(PivotType.LOW,2,100),pivot(PivotType.HIGH,4,110),pivot(PivotType.LOW,6,101)]
    bad_tf=[replace(ps[0],timeframe=PositionTimeframe.M60),*ps[1:]]; bad_unconfirmed=[replace(ps[0],confirmed=False),*ps[1:]]
    assert evaluate(bad_tf).data_status is DataStatus.INVALID and evaluate(bad_unconfirmed).data_status is DataStatus.INVALID
    broken=with_prices(candles(),ps); broken[0]=replace(broken[0],close=999)
    assert evaluate(ps,cs=broken).data_status is DataStatus.INVALID

def test_all_timeframes_isolate_failure() -> None:
    ps=[pivot(PivotType.LOW,2,100),pivot(PivotType.HIGH,4,110),pivot(PivotType.LOW,6,101)]
    valid=with_prices(candles(),ps)
    out=evaluate_all_structures({PositionTimeframe.M15:valid,PositionTimeframe.M60:[valid[0]]},{PositionTimeframe.M15:105,PositionTimeframe.M60:105},NOW,cfg(),{PositionTimeframe.M15:ps})
    assert set(out)==set(PositionTimeframe) and out[PositionTimeframe.M15].pivot_count>=3
    assert out[PositionTimeframe.M60].data_status is DataStatus.INSUFFICIENT_DATA and out[PositionTimeframe.D1].data_status is DataStatus.INVALID

def test_invalid_config_rejected() -> None:
    with pytest.raises(ValueError): cfg(minimum_leg_separation_bars_by_timeframe={t:9 for t in PositionTimeframe},maximum_leg_separation_bars_by_timeframe={t:2 for t in PositionTimeframe})
