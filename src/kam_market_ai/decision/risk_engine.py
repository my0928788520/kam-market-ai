"""Read-only, deterministic risk diagnostics for Contract and Confidence 1.0."""
from __future__ import annotations
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from enum import StrEnum
from typing import Mapping
from ..analysis.position_engine import ALL_TIMEFRAMES, PositionTimeframe
from .decision_contract import DECISION_INPUT_CONTRACT_VERSION, DecisionInputContract, DecisionInputStatus, DecisionModuleType, NormalizedModuleState
from .decision_confidence import DECISION_CONFIDENCE_ENGINE_VERSION, DecisionConfidenceResult, DecisionConfidenceState, TimeframeAlignmentState

RISK_ENGINE_VERSION="1.0"; Z=Decimal("0"); H=Decimal("100")
class RiskLevel(StrEnum): MINIMAL="minimal"; LOW="low"; MODERATE="moderate"; ELEVATED="elevated"; HIGH="high"; CRITICAL="critical"; UNAVAILABLE="unavailable"; STALE="stale"; INVALID="invalid"; CALCULATION_ERROR="calculation_error"
class RiskOperationalState(StrEnum): VALID="valid"; PROVISIONAL="provisional"; WAITING="waiting"; CONFLICTING="conflicting"; STALE="stale"; INSUFFICIENT="insufficient"; INVALID="invalid"; CALCULATION_ERROR="calculation_error"
class RiskCategory(StrEnum): DATA_QUALITY="data_quality"; TIMING="timing"; POSITION="position"; TREND="trend"; STRUCTURE="structure"; MODULE_CONFLICT="module_conflict"; TIMEFRAME_CONFLICT="timeframe_conflict"; HIGHER_TIMEFRAME_CONFLICT="higher_timeframe_conflict"; CONFIRMATION="confirmation"; COVERAGE="coverage"; SOURCE_INTEGRITY="source_integrity"
class RiskReasonCode(StrEnum): STALE_DATA="stale_data"; INVALID_SOURCE="invalid_source"; WAIT_FOR_CLOSE="wait_for_close"; PROVISIONAL_TIMING="provisional_timing"; MODULE_CONFLICT="module_conflict"; TIMEFRAME_CONFLICT="timeframe_conflict"; HIGHER_TIMEFRAME_CONFLICT="higher_timeframe_conflict"; INSUFFICIENT_COVERAGE="insufficient_coverage"; SOURCE_MISMATCH="source_mismatch"; CONFIDENCE_UNCERTAINTY="confidence_uncertainty"
@dataclass(frozen=True,slots=True)
class RiskEngineConfig:
    supported_contract_versions:frozenset[str]=frozenset({DECISION_INPUT_CONTRACT_VERSION}); supported_confidence_versions:frozenset[str]=frozenset({DECISION_CONFIDENCE_ENGINE_VERSION})
    category_weights:Mapping[RiskCategory,Decimal]=None; timeframe_weights:Mapping[PositionTimeframe,Decimal]=None
    risk_thresholds:tuple[Decimal,Decimal,Decimal,Decimal,Decimal]=(Decimal("15"),Decimal("30"),Decimal("50"),Decimal("70"),Decimal("85")); stale_floor:Decimal=Decimal("65"); conflict_floor:Decimal=Decimal("50"); missing_direction_floor:Decimal=Decimal("40"); wait_for_close_floor:Decimal=Decimal("30"); decimal_precision:int=2
    def __post_init__(self)->None:
        if self.category_weights is None: object.__setattr__(self,"category_weights",{RiskCategory.DATA_QUALITY:Decimal(".20"),RiskCategory.TIMING:Decimal(".15"),RiskCategory.POSITION:Decimal(".15"),RiskCategory.TREND:Decimal(".10"),RiskCategory.STRUCTURE:Decimal(".15"),RiskCategory.MODULE_CONFLICT:Decimal(".15"),RiskCategory.COVERAGE:Decimal(".10")})
        if self.timeframe_weights is None: object.__setattr__(self,"timeframe_weights",{PositionTimeframe.M5:Decimal(".10"),PositionTimeframe.M15:Decimal(".15"),PositionTimeframe.M60:Decimal(".25"),PositionTimeframe.D1:Decimal(".30"),PositionTimeframe.W1:Decimal(".20")})
        if sum(self.category_weights.values())!=Decimal("1") or sum(self.timeframe_weights.values())!=Decimal("1"): raise ValueError("Risk weights must total exactly 1.")
        if len(self.risk_thresholds)!=5 or not (Z<=self.risk_thresholds[0]<self.risk_thresholds[1]<self.risk_thresholds[2]<self.risk_thresholds[3]<self.risk_thresholds[4]<=H): raise ValueError("Invalid risk thresholds.")
    @classmethod
    def provisional(cls)->"RiskEngineConfig":return cls()
@dataclass(frozen=True,slots=True)
class RiskContribution: category:RiskCategory; timeframe:PositionTimeframe|None; source_module:DecisionModuleType|None; base_risk:Decimal; severity_multiplier:Decimal; quality_multiplier:Decimal; effective_risk:Decimal; capped:bool; included:bool; reason_code:RiskReasonCode; raw_state:str|None; raw_status:str|None; warnings:tuple[str,...]
@dataclass(frozen=True,slots=True)
class TimeframeRiskResult: timeframe:PositionTimeframe; risk_score:Decimal; risk_level:RiskLevel; operational_state:RiskOperationalState; data_quality_risk:Decimal; timing_risk:Decimal; position_risk:Decimal; trend_risk:Decimal; structure_risk:Decimal; module_conflict_risk:Decimal; coverage_risk:Decimal; contribution_count:int; contributions:tuple[RiskContribution,...]; major_risks:tuple[RiskReasonCode,...]; mitigating_factors:tuple[str,...]; valid:bool; warnings:tuple[str,...]; error_codes:tuple[str,...]
@dataclass(frozen=True,slots=True)
class RiskResult: engine_version:str; contract_version:str; confidence_engine_version:str; evaluated_at:object; overall_risk_score:Decimal; overall_risk_level:RiskLevel; operational_state:RiskOperationalState; timeframe_risks:Mapping[PositionTimeframe,TimeframeRiskResult]; timeframe_conflict_risk:Decimal; higher_timeframe_conflict_risk:Decimal; data_integrity_risk:Decimal; usable_timeframe_count:int; valid_timeframe_count:int; critical_timeframe_count:int; major_risks:tuple[RiskReasonCode,...]; mitigating_factors:tuple[str,...]; contributions:tuple[RiskContribution,...]; valid:bool; warnings:tuple[str,...]; error_codes:tuple[str,...]
def _level(x:Decimal,c:RiskEngineConfig)->RiskLevel:
    a,b,d,e,f=c.risk_thresholds;return RiskLevel.CRITICAL if x>=f else RiskLevel.HIGH if x>=e else RiskLevel.ELEVATED if x>=d else RiskLevel.MODERATE if x>=b else RiskLevel.LOW if x>=a else RiskLevel.MINIMAL
def _con(cat,tf,value,reason,module=None):return RiskContribution(cat,tf,module,value,Decimal("1"),Decimal("1"),value,False,value>Z,reason,None,None,())
def _invalid(contract,confidence,code):return RiskResult(RISK_ENGINE_VERSION,getattr(contract,"contract_version","?"),getattr(confidence,"engine_version","?"),getattr(contract,"evaluated_at",None),H,RiskLevel.INVALID,RiskOperationalState.INVALID,{},Z,Z,H,0,0,0,(),(),(),False,(),(code,))
def evaluate_risk(contract:DecisionInputContract,confidence:DecisionConfidenceResult,config:RiskEngineConfig)->RiskResult:
    if not isinstance(contract,DecisionInputContract) or not isinstance(confidence,DecisionConfidenceResult): raise TypeError("contract and confidence must use supported result types")
    if contract.contract_version not in config.supported_contract_versions or confidence.engine_version not in config.supported_confidence_versions:return _invalid(contract,confidence,"unsupported_source_version")
    if contract.evaluated_at!=confidence.evaluated_at or getattr(contract.evaluated_at,"tzinfo",None) is None:return _invalid(contract,confidence,"source_mismatch")
    results={}; allc=[]
    for tf in ALL_TIMEFRAMES:
        frame=contract.timeframes.get(tf); cr=confidence.timeframe_results.get(tf)
        if frame is None or cr is None: results[tf]=TimeframeRiskResult(tf,H,RiskLevel.INVALID,RiskOperationalState.INVALID,H,Z,Z,Z,Z,Z,H,0,(),(RiskReasonCode.SOURCE_MISMATCH,),(),False,(),("missing_timeframe",));continue
        data=H if frame.input_status is DecisionInputStatus.INVALID else Decimal("80") if frame.input_status is DecisionInputStatus.STALE else Z
        timing=Decimal("35") if frame.timing.normalized_state is NormalizedModuleState.WAITING else Decimal("20") if frame.timing.normalized_state is NormalizedModuleState.PROVISIONAL else Decimal("45") if frame.timing.normalized_state is NormalizedModuleState.STALE else Z
        conflict=Decimal("60") if cr.direction.value=="mixed" else Z; coverage=Decimal("50") if not frame.complete else Z
        uncertainty=max(Z,H-cr.confidence_score); score=(data*config.category_weights[RiskCategory.DATA_QUALITY]+timing*config.category_weights[RiskCategory.TIMING]+conflict*config.category_weights[RiskCategory.MODULE_CONFLICT]+coverage*config.category_weights[RiskCategory.COVERAGE]+uncertainty*Decimal(".30"));
        if data>=Decimal("80"):score=max(score,config.stale_floor)
        if conflict:score=max(score,config.conflict_floor)
        if timing>=Decimal("35"):score=max(score,config.wait_for_close_floor)
        score=min(H,score).quantize(Decimal(".01"),rounding=ROUND_HALF_UP); state=RiskOperationalState.INVALID if data==H else RiskOperationalState.STALE if data else RiskOperationalState.CONFLICTING if conflict else RiskOperationalState.WAITING if timing>=Decimal("35") else RiskOperationalState.PROVISIONAL if timing else RiskOperationalState.VALID
        cs=tuple(x for x in (_con(RiskCategory.DATA_QUALITY,tf,data,RiskReasonCode.INVALID_SOURCE) if data else None,_con(RiskCategory.TIMING,tf,timing,RiskReasonCode.WAIT_FOR_CLOSE) if timing else None,_con(RiskCategory.MODULE_CONFLICT,tf,conflict,RiskReasonCode.MODULE_CONFLICT) if conflict else None,_con(RiskCategory.COVERAGE,tf,coverage,RiskReasonCode.INSUFFICIENT_COVERAGE) if coverage else None) if x);allc.extend(cs)
        results[tf]=TimeframeRiskResult(tf,score,_level(score,config),state,data,timing,Z,Z,Z,conflict,coverage,len(cs),cs,tuple(x.reason_code for x in cs),(),state is RiskOperationalState.VALID,frame.warnings,frame.error_codes)
    score=sum(results[t].risk_score*config.timeframe_weights[t] for t in ALL_TIMEFRAMES); tf_conf=Decimal("60") if confidence.alignment_state is TimeframeAlignmentState.CONFLICTING else Z; higher=Decimal("75") if any(results[t].operational_state is RiskOperationalState.CONFLICTING for t in (PositionTimeframe.D1,PositionTimeframe.W1)) else Z; score=max(score,tf_conf,higher).quantize(Decimal(".01")); op=RiskOperationalState.INVALID if any(r.operational_state is RiskOperationalState.INVALID for r in results.values()) else RiskOperationalState.STALE if any(r.operational_state is RiskOperationalState.STALE for r in results.values()) else RiskOperationalState.CONFLICTING if tf_conf else RiskOperationalState.PROVISIONAL if any(r.operational_state in {RiskOperationalState.PROVISIONAL,RiskOperationalState.WAITING} for r in results.values()) else RiskOperationalState.VALID
    return RiskResult(RISK_ENGINE_VERSION,contract.contract_version,confidence.engine_version,contract.evaluated_at,score,RiskLevel.INVALID if op is RiskOperationalState.INVALID else RiskLevel.STALE if op is RiskOperationalState.STALE else _level(score,config),op,results,tf_conf,higher,Z,sum(r.operational_state is not RiskOperationalState.INVALID for r in results.values()),sum(r.valid for r in results.values()),sum(r.risk_level is RiskLevel.CRITICAL for r in results.values()),tuple(dict.fromkeys(x.reason_code for x in allc)),(),tuple(allc),op is RiskOperationalState.VALID,(),())
