"""Normalize existing Engine results; this module intentionally makes no decision."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Mapping

from ..analysis.position_engine import ALL_TIMEFRAMES, DataStatus, PositionRangeResult, PositionTimeframe, RangeState
from ..analysis.structure_engine import PatternState, PatternType, SequenceState, StructureResult
from ..analysis.timing_engine import TimingReadiness, TimingResult
from ..analysis.trend_engine import TrendState, TrendlineResult, TrendlineType

DECISION_INPUT_CONTRACT_VERSION = "1.0"

class DecisionModuleType(StrEnum): POSITION="position"; TREND="trend"; STRUCTURE="structure"; TIMING="timing"
class NormalizedModuleState(StrEnum): BULLISH="bullish"; BEARISH="bearish"; NEUTRAL="neutral"; SUPPORTIVE="supportive"; CONFLICTING="conflicting"; CONFIRMED="confirmed"; PROVISIONAL="provisional"; WAITING="waiting"; STALE="stale"; INSUFFICIENT="insufficient"; AMBIGUOUS="ambiguous"; INVALID="invalid"; UNAVAILABLE="unavailable"; CALCULATION_ERROR="calculation_error"; UNKNOWN="unknown"
class ModuleConfirmationState(StrEnum): CONFIRMED="confirmed"; PROVISIONAL="provisional"; WAITING="waiting"; UNAVAILABLE="unavailable"; INVALID="invalid"
class DecisionInputStatus(StrEnum): READY="ready"; PROVISIONAL="provisional"; PARTIAL="partial"; STALE="stale"; AMBIGUOUS="ambiguous"; INVALID="invalid"; UNAVAILABLE="unavailable"; CALCULATION_ERROR="calculation_error"
class MarketClosedPolicy(StrEnum): WAITING="waiting"; UNAVAILABLE="unavailable"
class UnknownStatePolicy(StrEnum): FAIL_CLOSED="fail_closed"

@dataclass(frozen=True, slots=True)
class DecisionInputConfig:
    required_modules: frozenset[DecisionModuleType]=frozenset(DecisionModuleType)
    required_timeframes: tuple[PositionTimeframe,...]=ALL_TIMEFRAMES
    minimum_usable_modules_per_timeframe: int=4
    timing_confirmation_required: bool=True
    allow_provisional_input: bool=True
    allow_partial_timeframes: bool=True
    stale_policy: UnknownStatePolicy=UnknownStatePolicy.FAIL_CLOSED
    ambiguous_policy: UnknownStatePolicy=UnknownStatePolicy.FAIL_CLOSED
    market_closed_policy: MarketClosedPolicy=MarketClosedPolicy.WAITING
    unknown_state_policy: UnknownStatePolicy=UnknownStatePolicy.FAIL_CLOSED
    fail_on_contract_version_mismatch: bool=True
    preserve_raw_payload: bool=True
    warning_limit: int=32
    def __post_init__(self)->None:
        if not self.required_modules or not self.required_timeframes or any(tf not in ALL_TIMEFRAMES for tf in self.required_timeframes): raise ValueError("Required modules/timeframes must be non-empty supported values.")
        if not 1<=self.minimum_usable_modules_per_timeframe<=len(self.required_modules): raise ValueError("minimum usable modules is out of range.")
        if self.warning_limit<=0: raise ValueError("warning_limit must be positive.")
    @classmethod
    def provisional(cls)->"DecisionInputConfig": return cls()

@dataclass(frozen=True, slots=True)
class DecisionModuleInput:
    module: DecisionModuleType; timeframe: PositionTimeframe; available: bool; valid: bool; data_status: DataStatus|None; normalized_state: NormalizedModuleState; confirmation_state: ModuleConfirmationState; confidence_hint: object|None; source_result_type: str|None; source_version: str; evaluated_at: datetime|None; warnings: tuple[str,...]; error_code: str|None; raw_state: str|None=None; raw_status: str|None=None
@dataclass(frozen=True, slots=True)
class TimeframeDecisionInput:
    timeframe: PositionTimeframe; position: DecisionModuleInput; trend: DecisionModuleInput; structure: DecisionModuleInput; timing: DecisionModuleInput; input_status: DecisionInputStatus; complete: bool; usable: bool; evaluated_at: datetime; warnings: tuple[str,...]; error_codes: tuple[str,...]
@dataclass(frozen=True, slots=True)
class DecisionInputContract:
    contract_version: str; generated_at: datetime; evaluated_at: datetime; timeframes: Mapping[PositionTimeframe,TimeframeDecisionInput]; overall_status: DecisionInputStatus; complete_timeframe_count: int; usable_timeframe_count: int; warnings: tuple[str,...]; error_codes: tuple[str,...]; source_versions: Mapping[DecisionModuleType,str]

def _state_from_status(status:DataStatus)->NormalizedModuleState|None:
    return {DataStatus.INSUFFICIENT_DATA:NormalizedModuleState.INSUFFICIENT,DataStatus.STALE:NormalizedModuleState.STALE,DataStatus.INVALID:NormalizedModuleState.INVALID,DataStatus.CALCULATION_ERROR:NormalizedModuleState.CALCULATION_ERROR}.get(status)
def _missing(module:DecisionModuleType,tf:PositionTimeframe,error:str)->DecisionModuleInput:
    return DecisionModuleInput(module,tf,False,False,None,NormalizedModuleState.UNAVAILABLE,ModuleConfirmationState.UNAVAILABLE,None,None,"v3-sprint1",None,(),error)
def _base(module:DecisionModuleType,result:object,tf:PositionTimeframe,state:NormalizedModuleState,confirmation:ModuleConfirmationState,confidence:object|None=None)->DecisionModuleInput:
    status=getattr(result,"data_status",None); valid=bool(getattr(result,"valid",False)); warnings=tuple(getattr(result,"warnings",()))
    forced=_state_from_status(status) if isinstance(status,DataStatus) else NormalizedModuleState.INVALID
    if forced: state=forced
    return DecisionModuleInput(module,tf,True,valid and state not in {NormalizedModuleState.INVALID,NormalizedModuleState.STALE,NormalizedModuleState.CALCULATION_ERROR},status if isinstance(status,DataStatus) else None,state,confirmation,confidence,type(result).__name__,"v3-sprint1",getattr(result,"evaluated_at",None),warnings,None,str(getattr(result,"range_state",getattr(result,"trend_state",getattr(result,"sequence_state",getattr(result,"timing_readiness",None))))) if True else None,str(status) if status else None)

def normalize_position_result(result:object,tf:PositionTimeframe)->DecisionModuleInput:
    if not isinstance(result,PositionRangeResult): return _missing(DecisionModuleType.POSITION,tf,"invalid_position_result_type")
    state={RangeState.BREAKOUT_UP:NormalizedModuleState.SUPPORTIVE,RangeState.NEAR_HIGH:NormalizedModuleState.BULLISH,RangeState.UPPER_HALF:NormalizedModuleState.BULLISH,RangeState.MIDDLE:NormalizedModuleState.NEUTRAL,RangeState.LOWER_HALF:NormalizedModuleState.BEARISH,RangeState.NEAR_LOW:NormalizedModuleState.BEARISH,RangeState.BREAKDOWN_DOWN:NormalizedModuleState.BEARISH}.get(result.range_state,NormalizedModuleState.INSUFFICIENT)
    return _base(DecisionModuleType.POSITION,result,tf,state,ModuleConfirmationState.CONFIRMED)
def normalize_trend_result(result:object,tf:PositionTimeframe)->DecisionModuleInput:
    if not isinstance(result,TrendlineResult): return _missing(DecisionModuleType.TREND,tf,"invalid_trend_result_type")
    state=NormalizedModuleState.BULLISH if result.active_trendline_type is TrendlineType.ASCENDING else NormalizedModuleState.BEARISH if result.active_trendline_type is TrendlineType.DESCENDING else NormalizedModuleState.NEUTRAL
    if result.trend_state is TrendState.AMBIGUOUS: state=NormalizedModuleState.AMBIGUOUS
    return _base(DecisionModuleType.TREND,result,tf,state,ModuleConfirmationState.CONFIRMED,result.confidence)
def normalize_structure_result(result:object,tf:PositionTimeframe)->DecisionModuleInput:
    if not isinstance(result,StructureResult): return _missing(DecisionModuleType.STRUCTURE,tf,"invalid_structure_result_type")
    state=NormalizedModuleState.BULLISH if result.sequence_state is SequenceState.BULLISH_CONTINUATION or result.w_bottom.state is PatternState.CONFIRMED else NormalizedModuleState.BEARISH if result.sequence_state is SequenceState.BEARISH_CONTINUATION or result.m_top.state is PatternState.CONFIRMED else NormalizedModuleState.CONFLICTING if result.sequence_state is SequenceState.MIXED else NormalizedModuleState.AMBIGUOUS if result.sequence_state is SequenceState.AMBIGUOUS else NormalizedModuleState.PROVISIONAL if result.w_bottom.state in {PatternState.CANDIDATE,PatternState.NECKLINE_TESTING} or result.m_top.state in {PatternState.CANDIDATE,PatternState.NECKLINE_TESTING} else NormalizedModuleState.NEUTRAL
    confirm=ModuleConfirmationState.PROVISIONAL if state is NormalizedModuleState.PROVISIONAL else ModuleConfirmationState.CONFIRMED
    confidence=(result.neckline.confidence if result.neckline else None)
    return _base(DecisionModuleType.STRUCTURE,result,tf,state,confirm,confidence)
def normalize_timing_result(result:object,tf:PositionTimeframe,config:DecisionInputConfig)->DecisionModuleInput:
    if not isinstance(result,TimingResult): return _missing(DecisionModuleType.TIMING,tf,"invalid_timing_result_type")
    readiness=result.timing_readiness; state={TimingReadiness.CONFIRMED:NormalizedModuleState.CONFIRMED,TimingReadiness.PROVISIONAL:NormalizedModuleState.PROVISIONAL,TimingReadiness.WAIT_FOR_CLOSE:NormalizedModuleState.WAITING,TimingReadiness.MARKET_CLOSED:NormalizedModuleState.WAITING if config.market_closed_policy is MarketClosedPolicy.WAITING else NormalizedModuleState.UNAVAILABLE,TimingReadiness.DELAYED:NormalizedModuleState.STALE,TimingReadiness.STALE:NormalizedModuleState.STALE,TimingReadiness.INVALID:NormalizedModuleState.INVALID,TimingReadiness.CALCULATION_ERROR:NormalizedModuleState.CALCULATION_ERROR}.get(readiness,NormalizedModuleState.INSUFFICIENT)
    confirm=ModuleConfirmationState.CONFIRMED if state is NormalizedModuleState.CONFIRMED else ModuleConfirmationState.PROVISIONAL if state is NormalizedModuleState.PROVISIONAL else ModuleConfirmationState.WAITING if state in {NormalizedModuleState.WAITING,NormalizedModuleState.STALE} else ModuleConfirmationState.INVALID
    return _base(DecisionModuleType.TIMING,result,tf,state,confirm)

def _tf_status(items:tuple[DecisionModuleInput,...],config:DecisionInputConfig)->DecisionInputStatus:
    states={x.normalized_state for x in items}
    if NormalizedModuleState.INVALID in states:return DecisionInputStatus.INVALID
    if NormalizedModuleState.CALCULATION_ERROR in states:return DecisionInputStatus.CALCULATION_ERROR
    if NormalizedModuleState.STALE in states:return DecisionInputStatus.STALE
    if NormalizedModuleState.AMBIGUOUS in states:return DecisionInputStatus.AMBIGUOUS
    available=sum(x.available and x.normalized_state not in {NormalizedModuleState.UNAVAILABLE,NormalizedModuleState.INSUFFICIENT} for x in items)
    if available<config.minimum_usable_modules_per_timeframe:return DecisionInputStatus.UNAVAILABLE
    if any(not x.available or x.normalized_state is NormalizedModuleState.INSUFFICIENT for x in items):return DecisionInputStatus.PARTIAL
    if any(x.confirmation_state is not ModuleConfirmationState.CONFIRMED for x in items):return DecisionInputStatus.PROVISIONAL
    return DecisionInputStatus.READY

def build_decision_input_contract(position_results_by_timeframe:Mapping[PositionTimeframe,object],trend_results_by_timeframe:Mapping[PositionTimeframe,object],structure_results_by_timeframe:Mapping[PositionTimeframe,object],timing_results_by_timeframe:Mapping[PositionTimeframe,object],evaluated_at:datetime,config:DecisionInputConfig,contract_version:str=DECISION_INPUT_CONTRACT_VERSION)->DecisionInputContract:
    if contract_version!=DECISION_INPUT_CONTRACT_VERSION and config.fail_on_contract_version_mismatch: raise ValueError("Unsupported Decision Input Contract version.")
    if evaluated_at.tzinfo is None or evaluated_at.utcoffset() is None: raise ValueError("evaluated_at must be timezone-aware.")
    frames={}; all_warnings=[]; all_errors=[]
    for tf in config.required_timeframes:
        p=normalize_position_result(position_results_by_timeframe.get(tf),tf); t=normalize_trend_result(trend_results_by_timeframe.get(tf),tf); s=normalize_structure_result(structure_results_by_timeframe.get(tf),tf); ti=normalize_timing_result(timing_results_by_timeframe.get(tf),tf,config); items=(p,t,s,ti)
        mismatch=[f"{x.module.value}_evaluated_at_mismatch" for x in items if x.evaluated_at is not None and x.evaluated_at!=evaluated_at]
        status=DecisionInputStatus.INVALID if mismatch else _tf_status(items,config); warnings=tuple((w for x in items for w in x.warnings))[:config.warning_limit]; errors=tuple(x.error_code for x in items if x.error_code)+tuple(mismatch)
        frames[tf]=TimeframeDecisionInput(tf,p,t,s,ti,status,all(x.available for x in items),status in {DecisionInputStatus.READY,DecisionInputStatus.PROVISIONAL},evaluated_at,warnings,errors);all_warnings.extend(warnings);all_errors.extend(errors)
    statuses=[x.input_status for x in frames.values()]; rank={DecisionInputStatus.READY:0,DecisionInputStatus.PROVISIONAL:1,DecisionInputStatus.PARTIAL:2,DecisionInputStatus.AMBIGUOUS:3,DecisionInputStatus.STALE:4,DecisionInputStatus.CALCULATION_ERROR:5,DecisionInputStatus.INVALID:6,DecisionInputStatus.UNAVAILABLE:7}; overall=max(statuses,key=lambda x:rank[x])
    return DecisionInputContract(contract_version,evaluated_at,evaluated_at,frames,overall,sum(x.complete for x in frames.values()),sum(x.usable for x in frames.values()),tuple(all_warnings)[:config.warning_limit],tuple(all_errors),{m:"v3-sprint1" for m in DecisionModuleType})
