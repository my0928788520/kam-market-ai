from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, time, timedelta

import pytest

from kam_market_ai.analysis.position_engine import DataStatus, PositionTimeframe
from kam_market_ai.analysis.timing_engine import (CandleTimingState, FreshnessState, HolidayPolicy, MarketPhase, SessionSchedule, SessionType, TimingEngineConfig, TimingReadiness, TAIPEI, evaluate_all_timings, evaluate_timing)
from kam_market_ai.models import Candle, Instrument

MONDAY=date(2026,8,3)
def at(hour:int,minute:int=0, day:date=MONDAY)->datetime: return datetime.combine(day,time(hour,minute),TAIPEI)
def candle(start:datetime,end:datetime)->Candle: return Candle(Instrument.MTX,start,end,100,101,99,100,1)
def config(**overrides:object)->TimingEngineConfig:
    base=TimingEngineConfig.provisional()
    return replace(base,**overrides)

@pytest.mark.parametrize(("moment","session","phase","trade"),[
    (at(8,46),SessionType.DAY,MarketPhase.OPENING,MONDAY),(at(10),SessionType.DAY,MarketPhase.REGULAR,MONDAY),(at(13,31),SessionType.DAY,MarketPhase.PRE_CLOSE,MONDAY),
    (at(15,1),SessionType.NIGHT,MarketPhase.OPENING,date(2026,8,4)),(at(20),SessionType.NIGHT,MarketPhase.REGULAR,date(2026,8,4)),(at(4,50,date(2026,8,4)),SessionType.NIGHT,MarketPhase.PRE_CLOSE,date(2026,8,4)),
    (at(8,35),SessionType.PRE_OPEN,MarketPhase.PRE_OPEN,MONDAY),(at(13,50),SessionType.BREAK_PERIOD,MarketPhase.SESSION_TRANSITION,None),(at(14,30),SessionType.CLOSED,MarketPhase.CLOSED,None),
])
def test_session_phase_and_trading_date(moment,session,phase,trade) -> None:
    result=evaluate_timing(PositionTimeframe.M15,[candle(moment-timedelta(minutes=15),moment)],moment,config())
    assert (result.session_type,result.market_phase,result.trading_date)==(session,phase,trade)

def test_weekend_holiday_and_unknown_holiday_fail_closed() -> None:
    saturday=at(10,day=date(2026,8,1)); closed=evaluate_timing(PositionTimeframe.M15,[],saturday,config())
    known=evaluate_timing(PositionTimeframe.M15,[],at(10),config(session_schedule=SessionSchedule(holidays=frozenset({MONDAY})),holiday_policy=HolidayPolicy.CLOSED))
    unknown=evaluate_timing(PositionTimeframe.M15,[],at(10),config(session_schedule=SessionSchedule(holidays=frozenset({MONDAY}))))
    assert closed.timing_readiness is TimingReadiness.MARKET_CLOSED
    assert known.session_type is SessionType.CLOSED and unknown.session_type is SessionType.UNKNOWN

def test_candle_closed_forming_future_and_overdue() -> None:
    now=at(10)
    closed=evaluate_timing(PositionTimeframe.M15,[candle(at(9,45),now)],now,config())
    forming=evaluate_timing(PositionTimeframe.M15,[candle(at(9,55),at(10,10))],now,config())
    future=evaluate_timing(PositionTimeframe.M15,[candle(at(10,10),at(10,25))],now,config())
    overdue=evaluate_timing(PositionTimeframe.M15,[candle(at(8,45),at(9))],now,config())
    assert closed.candle_timing_state is CandleTimingState.CLOSED and closed.close_confirmation_available
    assert forming.candle_timing_state is CandleTimingState.FORMING and forming.timing_readiness is TimingReadiness.WAIT_FOR_CLOSE
    assert future.candle_timing_state is CandleTimingState.FUTURE and future.data_status is DataStatus.INVALID
    assert overdue.candle_timing_state is CandleTimingState.OVERDUE and overdue.timing_readiness is TimingReadiness.STALE

@pytest.mark.parametrize(("end","expected_state","expected_readiness"),[
    (at(9,58),FreshnessState.FRESH,TimingReadiness.CONFIRMED),(at(9,50),FreshnessState.DELAYED,TimingReadiness.DELAYED),(at(9,20),FreshnessState.STALE,TimingReadiness.STALE),
])
def test_freshness_readiness(end,expected_state,expected_readiness) -> None:
    result=evaluate_timing(PositionTimeframe.M15,[candle(end-timedelta(minutes=15),end)],at(10),config())
    assert result.freshness_state is expected_state and result.timing_readiness is expected_readiness

def test_daily_forming_can_be_provisional() -> None:
    now=at(10); result=evaluate_timing(PositionTimeframe.D1,[candle(at(9),at(13,45))],now,config())
    assert result.timing_readiness is TimingReadiness.PROVISIONAL and not result.close_confirmation_available

def test_invalid_datetime_and_candle_sequence_are_rejected() -> None:
    naive=datetime(2026,8,3,10); now=at(10)
    bad_duration=candle(now,now); overlap=[candle(at(9),at(9,30)),candle(at(9,20),at(9,40))]
    assert evaluate_timing(PositionTimeframe.M15,[],naive,config()).data_status is DataStatus.INVALID
    assert evaluate_timing(PositionTimeframe.M15,[bad_duration],now,config()).data_status is DataStatus.INVALID
    assert evaluate_timing(PositionTimeframe.M15,overlap,now,config()).data_status is DataStatus.INVALID

def test_duplicate_sorting_and_aggregate_failure_isolation() -> None:
    now=at(10); later=candle(at(9,45),at(10)); earlier=candle(at(9,30),at(9,45)); duplicate=candle(at(9,30),at(9,45))
    sorted_result=evaluate_timing(PositionTimeframe.M15,[later,earlier],now,config())
    duplicate_result=evaluate_timing(PositionTimeframe.M15,[earlier,duplicate],now,config())
    all_results=evaluate_all_timings({PositionTimeframe.M15:[later],PositionTimeframe.M60:[bad for bad in [candle(now,now)]]},now,config())
    assert "candles_sorted_by_end" in sorted_result.warnings and duplicate_result.data_status is DataStatus.INVALID
    assert set(all_results)==set(PositionTimeframe) and all_results[PositionTimeframe.M15].data_status is DataStatus.OK and all_results[PositionTimeframe.M60].data_status is DataStatus.INVALID

def test_config_requires_complete_valid_mappings() -> None:
    with pytest.raises(ValueError): config(delayed_after_by_timeframe={})
