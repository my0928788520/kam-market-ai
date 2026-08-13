"""Offline, fail-closed Taiwan futures timing classification for KAM Trade V3."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from enum import StrEnum
from typing import Mapping, Sequence
from zoneinfo import ZoneInfo

from ..models import Candle
from .position_engine import ALL_TIMEFRAMES, DataStatus, PositionTimeframe

TAIPEI = ZoneInfo("Asia/Taipei")

class SessionType(StrEnum): DAY="day"; NIGHT="night"; CLOSED="closed"; PRE_OPEN="pre_open"; BREAK_PERIOD="break_period"; UNKNOWN="unknown"
class MarketPhase(StrEnum): PRE_OPEN="pre_open"; OPENING="opening"; REGULAR="regular"; PRE_CLOSE="pre_close"; CLOSED="closed"; SESSION_TRANSITION="session_transition"; UNKNOWN="unknown"; INVALID="invalid"
class CandleTimingState(StrEnum): CLOSED="closed"; FORMING="forming"; FUTURE="future"; OVERDUE="overdue"; MISSING="missing"; INVALID="invalid"
class FreshnessState(StrEnum): FRESH="fresh"; DELAYED="delayed"; STALE="stale"; FUTURE="future"; UNKNOWN="unknown"; INVALID="invalid"
class TimingReadiness(StrEnum): CONFIRMED="confirmed"; PROVISIONAL="provisional"; WAIT_FOR_CLOSE="wait_for_close"; MARKET_CLOSED="market_closed"; DELAYED="delayed"; STALE="stale"; INSUFFICIENT_DATA="insufficient_data"; AMBIGUOUS="ambiguous"; INVALID="invalid"; CALCULATION_ERROR="calculation_error"
class DuplicateTimestampPolicy(StrEnum): REJECT="reject"; KEEP_FIRST="keep_first"; KEEP_LAST="keep_last"
class TradingDatePolicy(StrEnum): NIGHT_SESSION_BELONGS_TO_NEXT_DAY="night_session_belongs_to_next_day"
class WeekendPolicy(StrEnum): CLOSED="closed"; UNKNOWN="unknown"
class HolidayPolicy(StrEnum): CLOSED="closed"; UNKNOWN="unknown"

@dataclass(frozen=True, slots=True)
class SessionSchedule:
    timezone: ZoneInfo=TAIPEI
    day_session_start: time=time(8,45)
    day_session_end: time=time(13,45)
    night_session_start: time=time(15,0)
    night_session_end: time=time(5,0)
    pre_open_window: timedelta=timedelta(minutes=15)
    opening_window: timedelta=timedelta(minutes=15)
    pre_close_window: timedelta=timedelta(minutes=15)
    holidays: frozenset[date]=frozenset()
    exceptional_sessions: Mapping[date, tuple[time,time,SessionType]]=None  # explicit adapter boundary
    weekend_policy: WeekendPolicy=WeekendPolicy.CLOSED
    def __post_init__(self) -> None:
        if self.timezone.key != "Asia/Taipei": raise ValueError("Timing Engine timezone must be Asia/Taipei.")
        if not (self.day_session_start < self.day_session_end and self.night_session_start > self.night_session_end): raise ValueError("Invalid provisional session boundaries.")
        if any(x <= timedelta(0) for x in (self.pre_open_window,self.opening_window,self.pre_close_window)): raise ValueError("Session windows must be positive.")
        if self.exceptional_sessions is None: object.__setattr__(self,"exceptional_sessions",{})

@dataclass(frozen=True, slots=True)
class TimingEngineConfig:
    timezone: ZoneInfo
    session_schedule: SessionSchedule
    pre_open_minutes: int
    opening_minutes: int
    pre_close_minutes: int
    delayed_after_by_timeframe: Mapping[PositionTimeframe,timedelta]
    stale_after_by_timeframe: Mapping[PositionTimeframe,timedelta]
    overdue_grace_by_timeframe: Mapping[PositionTimeframe,timedelta]
    require_closed_candle_by_timeframe: Mapping[PositionTimeframe,bool]
    trading_date_policy: TradingDatePolicy=TradingDatePolicy.NIGHT_SESSION_BELONGS_TO_NEXT_DAY
    weekend_policy: WeekendPolicy=WeekendPolicy.CLOSED
    holiday_policy: HolidayPolicy=HolidayPolicy.UNKNOWN
    allow_sort_input: bool=True
    duplicate_timestamp_policy: DuplicateTimestampPolicy=DuplicateTimestampPolicy.REJECT
    reject_naive_datetime: bool=True
    future_timestamp_tolerance: timedelta=timedelta(0)
    session_transition_grace: timedelta=timedelta(minutes=15)
    def __post_init__(self) -> None:
        if self.timezone.key != "Asia/Taipei" or self.session_schedule.timezone != self.timezone: raise ValueError("Config and schedule must use Asia/Taipei.")
        if any(not isinstance(v,int) or v <= 0 for v in (self.pre_open_minutes,self.opening_minutes,self.pre_close_minutes)): raise ValueError("Timing minute windows must be positive integers.")
        for values in (self.delayed_after_by_timeframe,self.stale_after_by_timeframe,self.overdue_grace_by_timeframe,self.require_closed_candle_by_timeframe):
            if set(ALL_TIMEFRAMES).difference(values): raise ValueError("Timing config is missing one or more timeframes.")
        for tf in ALL_TIMEFRAMES:
            delay=self.delayed_after_by_timeframe[tf]; stale=self.stale_after_by_timeframe[tf]; grace=self.overdue_grace_by_timeframe[tf]
            if not all(isinstance(x,timedelta) and x>timedelta(0) for x in (delay,stale,grace)) or delay>=stale: raise ValueError(f"Invalid freshness configuration for {tf.value}.")
            if not isinstance(self.require_closed_candle_by_timeframe[tf],bool): raise ValueError("require_closed_candle values must be bool.")
        if self.future_timestamp_tolerance < timedelta(0) or self.session_transition_grace < timedelta(0): raise ValueError("Timing tolerances cannot be negative.")
    @classmethod
    def provisional(cls) -> "TimingEngineConfig":
        m=lambda a,b,c,d,e:{PositionTimeframe.M5:a,PositionTimeframe.M15:b,PositionTimeframe.M60:c,PositionTimeframe.D1:d,PositionTimeframe.W1:e}
        schedule=SessionSchedule()
        return cls(TAIPEI,schedule,15,15,15,m(timedelta(minutes=2),timedelta(minutes=5),timedelta(minutes=15),timedelta(hours=6),timedelta(days=2)),m(timedelta(minutes=10),timedelta(minutes=30),timedelta(hours=2),timedelta(days=2),timedelta(days=14)),m(timedelta(minutes=1),timedelta(minutes=2),timedelta(minutes=5),timedelta(hours=1),timedelta(days=1)),m(True,True,True,False,False))

@dataclass(frozen=True, slots=True)
class TimingResult:
    timeframe: PositionTimeframe; evaluated_at: datetime; timezone: str; calendar_date: date|None; trading_date: date|None; session_type: SessionType; market_phase: MarketPhase; session_start: datetime|None; session_end: datetime|None; minutes_from_open: int|None; minutes_to_close: int|None; candle_timing_state: CandleTimingState; candle_start: datetime|None; candle_end: datetime|None; expected_close_at: datetime|None; seconds_until_close: int|None; seconds_since_close: int|None; is_closed: bool; is_forming: bool; close_confirmation_available: bool; freshness_state: FreshnessState; latest_data_at: datetime|None; data_age_seconds: int|None; timing_readiness: TimingReadiness; data_status: DataStatus; valid: bool; warnings: tuple[str,...]

def _aware(value: datetime) -> bool: return value.tzinfo is not None and value.utcoffset() is not None
def _combine(day:date, clock:time, tz:ZoneInfo)->datetime: return datetime.combine(day,clock,tzinfo=tz)

def _session(at:datetime,cfg:TimingEngineConfig)->tuple[SessionType,MarketPhase,datetime|None,datetime|None,date|None]:
    local=at.astimezone(cfg.timezone); d=local.date(); t=local.timetz().replace(tzinfo=None); s=cfg.session_schedule
    if d in s.holidays: return (SessionType.CLOSED if cfg.holiday_policy is HolidayPolicy.CLOSED else SessionType.UNKNOWN,MarketPhase.CLOSED if cfg.holiday_policy is HolidayPolicy.CLOSED else MarketPhase.UNKNOWN,None,None,None)
    if d.weekday()>=5 and cfg.weekend_policy is WeekendPolicy.CLOSED: return SessionType.CLOSED,MarketPhase.CLOSED,None,None,None
    if d in s.exceptional_sessions:
        start,end,typ=s.exceptional_sessions[d]; begin=_combine(d,start,cfg.timezone); finish=_combine(d,end,cfg.timezone); return typ,MarketPhase.REGULAR,begin,finish,d
    day_start=_combine(d,s.day_session_start,cfg.timezone); day_end=_combine(d,s.day_session_end,cfg.timezone)
    night_start=_combine(d,s.night_session_start,cfg.timezone); night_end=_combine(d,s.night_session_end,cfg.timezone)
    if day_start-timedelta(minutes=cfg.pre_open_minutes) <= local < day_start: return SessionType.PRE_OPEN,MarketPhase.PRE_OPEN,day_start,day_end,d
    if day_start <= local < day_end: return SessionType.DAY,(MarketPhase.OPENING if local<day_start+timedelta(minutes=cfg.opening_minutes) else MarketPhase.PRE_CLOSE if local>=day_end-timedelta(minutes=cfg.pre_close_minutes) else MarketPhase.REGULAR),day_start,day_end,d
    if night_start-timedelta(minutes=cfg.pre_open_minutes) <= local < night_start: return SessionType.PRE_OPEN,MarketPhase.PRE_OPEN,night_start,night_end+timedelta(days=1),d+timedelta(days=1)
    if t>=s.night_session_start or t<s.night_session_end:
        start=night_start if t>=s.night_session_start else _combine(d-timedelta(days=1),s.night_session_start,cfg.timezone); end=start.replace(hour=s.night_session_end.hour,minute=s.night_session_end.minute)+timedelta(days=1)
        trade=start.date()+timedelta(days=1); phase=MarketPhase.OPENING if local<start+timedelta(minutes=cfg.opening_minutes) else MarketPhase.PRE_CLOSE if local>=end-timedelta(minutes=cfg.pre_close_minutes) else MarketPhase.REGULAR
        return SessionType.NIGHT,phase,start,end,trade
    if day_end <= local < day_end+cfg.session_transition_grace or night_end <= local < night_end+cfg.session_transition_grace: return SessionType.BREAK_PERIOD,MarketPhase.SESSION_TRANSITION,None,None,None
    return SessionType.CLOSED,MarketPhase.CLOSED,None,None,None

def _error(tf:PositionTimeframe,at:datetime,warning:str,status:DataStatus=DataStatus.INVALID)->TimingResult:
    return TimingResult(tf,at,"Asia/Taipei",None,None,SessionType.UNKNOWN,MarketPhase.INVALID,None,None,None,None,CandleTimingState.INVALID,None,None,None,None,None,False,False,False,FreshnessState.INVALID,None,None,TimingReadiness.INVALID if status is DataStatus.INVALID else TimingReadiness.INSUFFICIENT_DATA,status,False,(warning,))

def evaluate_timing(timeframe:PositionTimeframe,candles:Sequence[Candle],evaluated_at:datetime,config:TimingEngineConfig)->TimingResult:
    if not _aware(evaluated_at) and config.reject_naive_datetime: return _error(timeframe,evaluated_at,"naive_evaluated_at")
    if not _aware(evaluated_at): return _error(timeframe,evaluated_at,"naive_evaluated_at_not_supported")
    prepared=list(candles); warnings=[]
    try:
        if any(not isinstance(c,Candle) or not _aware(c.start) or not _aware(c.end) or c.start>=c.end for c in prepared): return _error(timeframe,evaluated_at,"invalid_candle")
        if any(c.start.tzinfo != evaluated_at.tzinfo and c.start.astimezone(config.timezone).utcoffset()!=evaluated_at.astimezone(config.timezone).utcoffset() for c in prepared): return _error(timeframe,evaluated_at,"incompatible_candle_timezone")
        if any(prepared[i].end>prepared[i+1].end for i in range(len(prepared)-1)):
            if not config.allow_sort_input:return _error(timeframe,evaluated_at,"candles_out_of_order")
            prepared.sort(key=lambda c:c.end);warnings.append("candles_sorted_by_end")
        if len({c.end for c in prepared})!=len(prepared):
            if config.duplicate_timestamp_policy is DuplicateTimestampPolicy.REJECT:return _error(timeframe,evaluated_at,"duplicate_candle_timestamp")
            keep={}
            for c in prepared:
                if config.duplicate_timestamp_policy is DuplicateTimestampPolicy.KEEP_FIRST: keep.setdefault(c.end,c)
                else: keep[c.end]=c
            prepared=list(keep.values());warnings.append("duplicate_candle_timestamp_resolved")
        if any(prepared[i].start<prepared[i-1].end for i in range(1,len(prepared))):return _error(timeframe,evaluated_at,"overlapping_candles")
    except (TypeError,ValueError): return _error(timeframe,evaluated_at,"incompatible_timestamp")
    sess,phase,start,end,trading=_session(evaluated_at,config); local=evaluated_at.astimezone(config.timezone)
    if not prepared:
        readiness=TimingReadiness.MARKET_CLOSED if sess is SessionType.CLOSED else TimingReadiness.INSUFFICIENT_DATA
        return TimingResult(timeframe,evaluated_at,"Asia/Taipei",local.date(),trading,sess,phase,start,end,None,None,CandleTimingState.MISSING,None,None,None,None,None,False,False,False,FreshnessState.UNKNOWN,None,None,readiness,DataStatus.INSUFFICIENT_DATA,False,tuple(warnings+["missing_latest_candle"]))
    latest=prepared[-1]; duration=latest.end-latest.start; future=latest.start>evaluated_at+config.future_timestamp_tolerance
    forming=latest.start<=evaluated_at<latest.end; closed=latest.end<=evaluated_at; overdue=closed and evaluated_at>latest.end+duration+config.overdue_grace_by_timeframe[timeframe]
    state=CandleTimingState.FUTURE if future else CandleTimingState.FORMING if forming else CandleTimingState.OVERDUE if overdue else CandleTimingState.CLOSED
    age=evaluated_at-latest.end
    freshness=FreshnessState.FUTURE if age < -config.future_timestamp_tolerance else FreshnessState.STALE if age>config.stale_after_by_timeframe[timeframe] else FreshnessState.DELAYED if age>config.delayed_after_by_timeframe[timeframe] else FreshnessState.FRESH
    status=DataStatus.STALE if freshness is FreshnessState.STALE else DataStatus.OK
    if future: status=DataStatus.INVALID
    if status is DataStatus.INVALID: readiness=TimingReadiness.INVALID
    elif sess is SessionType.CLOSED: readiness=TimingReadiness.MARKET_CLOSED
    elif freshness is FreshnessState.STALE or overdue: readiness=TimingReadiness.STALE; status=DataStatus.STALE
    elif freshness is FreshnessState.DELAYED: readiness=TimingReadiness.DELAYED
    elif forming: readiness=TimingReadiness.WAIT_FOR_CLOSE if config.require_closed_candle_by_timeframe[timeframe] else TimingReadiness.PROVISIONAL
    elif sess is SessionType.PRE_OPEN: readiness=TimingReadiness.PROVISIONAL
    else: readiness=TimingReadiness.CONFIRMED
    mins_open=int((local-start).total_seconds()//60) if start else None; mins_close=int((end-local).total_seconds()//60) if end else None
    return TimingResult(timeframe,evaluated_at,"Asia/Taipei",local.date(),trading,sess,phase,start,end,mins_open,mins_close,state,latest.start,latest.end,latest.end,int((latest.end-evaluated_at).total_seconds()) if forming else None,int(age.total_seconds()) if closed else None,closed,forming,closed and freshness is FreshnessState.FRESH,FreshnessState.UNKNOWN if sess is SessionType.CLOSED and freshness is FreshnessState.FRESH else freshness,latest.end,int(age.total_seconds()),readiness,status,readiness is TimingReadiness.CONFIRMED,tuple(warnings))

def evaluate_all_timings(candles_by_timeframe:Mapping[PositionTimeframe,Sequence[Candle]],evaluated_at:datetime,config:TimingEngineConfig)->dict[PositionTimeframe,TimingResult]:
    out={}
    for tf in ALL_TIMEFRAMES:
        try: out[tf]=evaluate_timing(tf,candles_by_timeframe.get(tf,()),evaluated_at,config)
        except Exception as exc: out[tf]=_error(tf,evaluated_at,f"unexpected_calculation_error:{type(exc).__name__}",DataStatus.CALCULATION_ERROR)
    return out
