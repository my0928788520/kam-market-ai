"""Deterministic, read-only confidence assessment over Decision Input Contract 1.0."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from enum import StrEnum
from typing import Mapping

from ..analysis.position_engine import ALL_TIMEFRAMES, PositionTimeframe
from .decision_contract import (DECISION_INPUT_CONTRACT_VERSION, DecisionInputContract, DecisionModuleInput, DecisionModuleType, DecisionInputStatus, ModuleConfirmationState, NormalizedModuleState)

DECISION_CONFIDENCE_ENGINE_VERSION="1.0"
ZERO=Decimal("0"); ONE=Decimal("1"); HUNDRED=Decimal("100")
class DecisionDirection(StrEnum): BULLISH="bullish"; BEARISH="bearish"; NEUTRAL="neutral"; MIXED="mixed"; UNAVAILABLE="unavailable"; INVALID="invalid"
class DecisionConfidenceState(StrEnum): VERY_HIGH="very_high"; HIGH="high"; MODERATE="moderate"; LOW="low"; VERY_LOW="very_low"; UNAVAILABLE="unavailable"; PROVISIONAL="provisional"; STALE="stale"; AMBIGUOUS="ambiguous"; CONFLICTING="conflicting"; INVALID="invalid"; CALCULATION_ERROR="calculation_error"
class TimeframeAlignmentState(StrEnum): FULLY_ALIGNED="fully_aligned"; MOSTLY_ALIGNED="mostly_aligned"; PARTIALLY_ALIGNED="partially_aligned"; CONFLICTING="conflicting"; NEUTRAL="neutral"; INSUFFICIENT="insufficient"; STALE="stale"; INVALID="invalid"
class ConfidenceHintOutOfRangePolicy(StrEnum): REJECT="reject"; CLAMP="clamp"
class ReasonCode(StrEnum): ALIGNED_TREND_STRUCTURE="aligned_trend_structure"; CONFIRMED_TIMING="confirmed_timing"; PROVISIONAL_TIMING="provisional_timing"; WAITING_FOR_CLOSE="waiting_for_close"; MARKET_CLOSED="market_closed"; DELAYED_DATA="delayed_data"; STALE_DATA="stale_data"; AMBIGUOUS_MODULE="ambiguous_module"; CONFLICTING_MODULES="conflicting_modules"; CONFLICTING_TIMEFRAMES="conflicting_timeframes"; HIGHER_TIMEFRAME_CONFLICT="higher_timeframe_conflict"; INSUFFICIENT_MODULES="insufficient_modules"; INSUFFICIENT_TIMEFRAMES="insufficient_timeframes"; NEUTRAL_MARKET="neutral_market"; INVALID_INPUT="invalid_input"; CONTRACT_VERSION_MISMATCH="contract_version_mismatch"; CALCULATION_ERROR="calculation_error"

@dataclass(frozen=True,slots=True)
class DecisionConfidenceConfig:
    supported_contract_versions:frozenset[str]=frozenset({DECISION_INPUT_CONTRACT_VERSION})
    module_weights:Mapping[DecisionModuleType,Decimal]=None
    timeframe_weights:Mapping[PositionTimeframe,Decimal]=None
    timing_multipliers:Mapping[NormalizedModuleState,Decimal]=None
    default_quality_by_confirmation:Mapping[ModuleConfirmationState,Decimal]=None
    confidence_thresholds:tuple[Decimal,Decimal,Decimal,Decimal]=(Decimal("85"),Decimal("70"),Decimal("50"),Decimal("30"))
    mixed_direction_margin:Decimal=Decimal("0.10")
    minimum_directional_modules:int=1; minimum_usable_modules_per_timeframe:int=2; minimum_usable_timeframes:int=1
    agreement_thresholds:tuple[Decimal,Decimal]=(Decimal("0.70"),Decimal("0.55"))
    conflict_penalty_weight:Decimal=Decimal("20"); ambiguity_penalty_weight:Decimal=Decimal("15")
    allow_provisional:bool=True; confidence_hint_min:Decimal=ZERO; confidence_hint_max:Decimal=ONE; confidence_hint_out_of_range_policy:ConfidenceHintOutOfRangePolicy=ConfidenceHintOutOfRangePolicy.REJECT; decimal_precision:int=2; warning_limit:int=32
    def __post_init__(self)->None:
        if self.module_weights is None: object.__setattr__(self,"module_weights",{DecisionModuleType.POSITION:Decimal(".20"),DecisionModuleType.TREND:Decimal(".35"),DecisionModuleType.STRUCTURE:Decimal(".35"),DecisionModuleType.TIMING:Decimal(".10")})
        if self.timeframe_weights is None: object.__setattr__(self,"timeframe_weights",{PositionTimeframe.M15:Decimal(".15"),PositionTimeframe.M60:Decimal(".25"),PositionTimeframe.D1:Decimal(".35"),PositionTimeframe.W1:Decimal(".25")})
        if self.timing_multipliers is None: object.__setattr__(self,"timing_multipliers",{NormalizedModuleState.CONFIRMED:ONE,NormalizedModuleState.PROVISIONAL:Decimal(".75"),NormalizedModuleState.WAITING:Decimal(".50"),NormalizedModuleState.STALE:ZERO,NormalizedModuleState.INVALID:ZERO,NormalizedModuleState.CALCULATION_ERROR:ZERO})
        if self.default_quality_by_confirmation is None: object.__setattr__(self,"default_quality_by_confirmation",{ModuleConfirmationState.CONFIRMED:ONE,ModuleConfirmationState.PROVISIONAL:Decimal(".75"),ModuleConfirmationState.WAITING:Decimal(".50"),ModuleConfirmationState.UNAVAILABLE:ZERO,ModuleConfirmationState.INVALID:ZERO})
        if set(self.module_weights)!=set(DecisionModuleType) or set(self.timeframe_weights)!=set(ALL_TIMEFRAMES): raise ValueError("Confidence config requires all fixed module/timeframe weights.")
        if any(not isinstance(x,Decimal) or not x.is_finite() or x<ZERO for x in (*self.module_weights.values(),*self.timeframe_weights.values(),*self.timing_multipliers.values(),*self.default_quality_by_confirmation.values())): raise ValueError("Weights must be finite non-negative Decimals.")
        if sum(self.module_weights.values())!=ONE or sum(self.timeframe_weights.values())!=ONE: raise ValueError("Module and timeframe weights must each total exactly 1.")
        if len(self.confidence_thresholds)!=4 or not (HUNDRED>=self.confidence_thresholds[0]>self.confidence_thresholds[1]>self.confidence_thresholds[2]>self.confidence_thresholds[3]>=ZERO): raise ValueError("Invalid confidence thresholds.")
        if not (ONE>=self.agreement_thresholds[0]>self.agreement_thresholds[1]>ZERO) or not ZERO<=self.mixed_direction_margin<=ONE: raise ValueError("Invalid agreement thresholds.")
        if min(self.minimum_directional_modules,self.minimum_usable_modules_per_timeframe,self.minimum_usable_timeframes,self.decimal_precision,self.warning_limit)<=0: raise ValueError("Minimums, precision, warning limit must be positive.")
    @classmethod
    def provisional(cls)->"DecisionConfidenceConfig": return cls()

@dataclass(frozen=True,slots=True)
class TimingConfidenceGate: state:NormalizedModuleState; multiplier:Decimal; reason:ReasonCode
@dataclass(frozen=True,slots=True)
class ModuleConfidenceContribution:
    module:DecisionModuleType; timeframe:PositionTimeframe; direction:DecisionDirection; base_weight:Decimal; quality_multiplier:Decimal; confirmation_multiplier:Decimal; effective_weight:Decimal; bullish_contribution:Decimal; bearish_contribution:Decimal; neutral_contribution:Decimal; penalty:Decimal; included:bool; exclusion_reason:str|None; raw_state:str|None; raw_status:str|None; warnings:tuple[str,...]
@dataclass(frozen=True,slots=True)
class TimeframeConfidenceResult:
    timeframe:PositionTimeframe; direction:DecisionDirection; confidence_score:Decimal; confidence_state:DecisionConfidenceState; bullish_score:Decimal; bearish_score:Decimal; neutral_score:Decimal; directional_margin:Decimal; agreement_ratio:Decimal; usable_module_count:int; directional_module_count:int; confirmed_module_count:int; provisional_module_count:int; conflicting_module_count:int; timing_gate:TimingConfidenceGate; contributions:tuple[ModuleConfidenceContribution,...]; penalties:tuple[str,...]; valid:bool; warnings:tuple[str,...]; error_codes:tuple[str,...]
@dataclass(frozen=True,slots=True)
class DecisionConfidenceResult:
    engine_version:str; contract_version:str; evaluated_at:object; overall_direction:DecisionDirection; overall_confidence_score:Decimal; overall_confidence_state:DecisionConfidenceState; score_level:DecisionConfidenceState; alignment_state:TimeframeAlignmentState; alignment_ratio:Decimal; bullish_timeframe_weight:Decimal; bearish_timeframe_weight:Decimal; neutral_timeframe_weight:Decimal; usable_timeframe_count:int; confirmed_timeframe_count:int; timeframe_results:Mapping[PositionTimeframe,TimeframeConfidenceResult]; major_supports:tuple[ReasonCode,...]; major_conflicts:tuple[ReasonCode,...]; penalties:tuple[str,...]; valid:bool; warnings:tuple[str,...]; error_codes:tuple[str,...]

def _decimal(value:object)->Decimal|None:
    try: out=Decimal(str(value))
    except (InvalidOperation,ValueError,TypeError): return None
    return out if out.is_finite() else None
def _clamp(value:Decimal)->Decimal:return max(ZERO,min(ONE,value))
def _direction(state:NormalizedModuleState)->DecisionDirection:return DecisionDirection.BULLISH if state in {NormalizedModuleState.BULLISH,NormalizedModuleState.SUPPORTIVE} else DecisionDirection.BEARISH if state is NormalizedModuleState.BEARISH else DecisionDirection.NEUTRAL
def _level(score:Decimal,cfg:DecisionConfidenceConfig)->DecisionConfidenceState:
    a,b,c,d=cfg.confidence_thresholds; return DecisionConfidenceState.VERY_HIGH if score>=a else DecisionConfidenceState.HIGH if score>=b else DecisionConfidenceState.MODERATE if score>=c else DecisionConfidenceState.LOW if score>=d else DecisionConfidenceState.VERY_LOW
def _gate(timing:DecisionModuleInput,cfg:DecisionConfidenceConfig)->TimingConfidenceGate:
    state=timing.normalized_state; mult=cfg.timing_multipliers.get(state,ZERO); reason=ReasonCode.CONFIRMED_TIMING if state is NormalizedModuleState.CONFIRMED else ReasonCode.PROVISIONAL_TIMING if state is NormalizedModuleState.PROVISIONAL else ReasonCode.WAITING_FOR_CLOSE if state is NormalizedModuleState.WAITING else ReasonCode.STALE_DATA if state is NormalizedModuleState.STALE else ReasonCode.INVALID_INPUT
    return TimingConfidenceGate(state,mult,reason)
def _contribution(item:DecisionModuleInput,cfg:DecisionConfidenceConfig,gate:TimingConfidenceGate)->ModuleConfidenceContribution:
    base=cfg.module_weights[item.module]; direction=_direction(item.normalized_state); hint=_decimal(item.confidence_hint); quality=cfg.default_quality_by_confirmation.get(item.confirmation_state,ZERO)
    excluded=None
    if hint is not None:
        if not cfg.confidence_hint_min<=hint<=cfg.confidence_hint_max:
            if cfg.confidence_hint_out_of_range_policy is ConfidenceHintOutOfRangePolicy.REJECT: excluded="confidence_hint_out_of_range"; quality=ZERO
            else: quality=_clamp(hint)
        else: quality=hint
    if item.normalized_state in {NormalizedModuleState.STALE,NormalizedModuleState.INVALID,NormalizedModuleState.CALCULATION_ERROR,NormalizedModuleState.UNAVAILABLE,NormalizedModuleState.INSUFFICIENT,NormalizedModuleState.AMBIGUOUS,NormalizedModuleState.CONFLICTING}: excluded=excluded or "non_directional_or_unusable_state"; quality=ZERO
    confirm=gate.multiplier if item.module is not DecisionModuleType.TIMING else ONE
    effective=base*quality*confirm; included=effective>ZERO and direction in {DecisionDirection.BULLISH,DecisionDirection.BEARISH}
    return ModuleConfidenceContribution(item.module,item.timeframe,direction,base,quality,confirm,effective,effective if direction is DecisionDirection.BULLISH and included else ZERO,effective if direction is DecisionDirection.BEARISH and included else ZERO,base*quality if direction is DecisionDirection.NEUTRAL else ZERO,ZERO,included,excluded,item.raw_state,item.raw_status,item.warnings)

def _empty(tf:PositionTimeframe,code:str)->TimeframeConfidenceResult:
    gate=TimingConfidenceGate(NormalizedModuleState.INVALID,ZERO,ReasonCode.INVALID_INPUT)
    return TimeframeConfidenceResult(tf,DecisionDirection.INVALID,ZERO,DecisionConfidenceState.INVALID,ZERO,ZERO,ZERO,ZERO,ZERO,0,0,0,0,0,gate,(),(),False,(),(code,))
def _timeframe(frame, cfg:DecisionConfidenceConfig)->TimeframeConfidenceResult:
    items=(frame.position,frame.trend,frame.structure,frame.timing); gate=_gate(frame.timing,cfg); cs=tuple(_contribution(x,cfg,gate) for x in items); bull=sum(x.bullish_contribution for x in cs); bear=sum(x.bearish_contribution for x in cs); neutral=sum(x.neutral_contribution for x in cs); directional=bull+bear; usable=sum(x.included for x in cs); confirmed=sum(x.confirmation_state is ModuleConfirmationState.CONFIRMED for x in items); provisional=sum(x.confirmation_state is not ModuleConfirmationState.CONFIRMED for x in items); ambiguous=sum(x.normalized_state in {NormalizedModuleState.AMBIGUOUS,NormalizedModuleState.CONFLICTING} for x in items)
    dominant=max(bull,bear); opposing=min(bull,bear); ratio=dominant/directional if directional else ZERO; margin=dominant-opposing
    direction=DecisionDirection.MIXED if bull>ZERO and bear>ZERO else DecisionDirection.BULLISH if bull>ZERO else DecisionDirection.BEARISH if bear>ZERO else DecisionDirection.NEUTRAL
    coverage=Decimal(usable)/Decimal(len(DecisionModuleType)); quality=(sum(x.quality_multiplier for x in cs)/Decimal(len(cs))); score=_clamp(dominant*ratio*quality*coverage*gate.multiplier)*HUNDRED; penalties=[]
    if opposing>ZERO: score=max(ZERO,score-cfg.conflict_penalty_weight*opposing);penalties.append("conflict_penalty")
    if ambiguous: score=max(ZERO,score-cfg.ambiguity_penalty_weight*Decimal(ambiguous)/Decimal(len(cs)));penalties.append("ambiguity_penalty")
    score=score.quantize(Decimal("1").scaleb(-cfg.decimal_precision),rounding=ROUND_HALF_UP)
    state=DecisionConfidenceState.INVALID if frame.input_status is DecisionInputStatus.INVALID else DecisionConfidenceState.CALCULATION_ERROR if frame.input_status is DecisionInputStatus.CALCULATION_ERROR else DecisionConfidenceState.STALE if frame.input_status is DecisionInputStatus.STALE else DecisionConfidenceState.AMBIGUOUS if frame.input_status is DecisionInputStatus.AMBIGUOUS else DecisionConfidenceState.PROVISIONAL if frame.input_status is DecisionInputStatus.PROVISIONAL or gate.multiplier<ONE else DecisionConfidenceState.UNAVAILABLE if usable<cfg.minimum_usable_modules_per_timeframe else DecisionConfidenceState.CONFLICTING if direction is DecisionDirection.MIXED else _level(score,cfg)
    return TimeframeConfidenceResult(frame.timeframe,direction,score,state,bull,bear,neutral,margin,ratio,usable,sum(x.included for x in cs),confirmed,provisional,ambiguous,gate,cs,tuple(penalties),state not in {DecisionConfidenceState.INVALID,DecisionConfidenceState.STALE,DecisionConfidenceState.CALCULATION_ERROR},frame.warnings,frame.error_codes)

def evaluate_decision_confidence(contract:DecisionInputContract,config:DecisionConfidenceConfig)->DecisionConfidenceResult:
    if not isinstance(contract,DecisionInputContract): raise TypeError("contract must be DecisionInputContract")
    if contract.contract_version not in config.supported_contract_versions: return DecisionConfidenceResult(DECISION_CONFIDENCE_ENGINE_VERSION,contract.contract_version,contract.evaluated_at,DecisionDirection.INVALID,ZERO,DecisionConfidenceState.INVALID,DecisionConfidenceState.INVALID,TimeframeAlignmentState.INVALID,ZERO,ZERO,ZERO,ZERO,0,0,{},(),(),(),False,(),("contract_version_mismatch",))
    if getattr(contract.evaluated_at,"tzinfo",None) is None or contract.evaluated_at.utcoffset() is None: return DecisionConfidenceResult(DECISION_CONFIDENCE_ENGINE_VERSION,contract.contract_version,contract.evaluated_at,DecisionDirection.INVALID,ZERO,DecisionConfidenceState.INVALID,DecisionConfidenceState.INVALID,TimeframeAlignmentState.INVALID,ZERO,ZERO,ZERO,ZERO,0,0,{},(),(),(),False,(),("naive_evaluated_at",))
    results={tf:_timeframe(contract.timeframes[tf],config) if tf in contract.timeframes else _empty(tf,"missing_timeframe") for tf in ALL_TIMEFRAMES}; bull=sum(config.timeframe_weights[tf] for tf,r in results.items() if r.direction is DecisionDirection.BULLISH); bear=sum(config.timeframe_weights[tf] for tf,r in results.items() if r.direction is DecisionDirection.BEARISH); neutral=sum(config.timeframe_weights[tf] for tf,r in results.items() if r.direction is DecisionDirection.NEUTRAL); usable=[r for r in results.values() if r.valid]; dominant=max(bull,bear); ratio=dominant/(bull+bear) if bull+bear else ZERO
    has_mixed=any(r.direction is DecisionDirection.MIXED for r in results.values())
    direction=DecisionDirection.MIXED if has_mixed else DecisionDirection.BULLISH if bull>bear and ratio>=config.agreement_thresholds[1] else DecisionDirection.BEARISH if bear>bull and ratio>=config.agreement_thresholds[1] else DecisionDirection.MIXED if bull+bear else DecisionDirection.NEUTRAL
    alignment=TimeframeAlignmentState.INVALID if any(r.confidence_state is DecisionConfidenceState.INVALID for r in results.values()) else TimeframeAlignmentState.STALE if any(r.confidence_state is DecisionConfidenceState.STALE for r in results.values()) else TimeframeAlignmentState.CONFLICTING if has_mixed else TimeframeAlignmentState.FULLY_ALIGNED if ratio==ONE and bull+bear>ZERO else TimeframeAlignmentState.MOSTLY_ALIGNED if ratio>=config.agreement_thresholds[0] else TimeframeAlignmentState.PARTIALLY_ALIGNED if ratio>=config.agreement_thresholds[1] else TimeframeAlignmentState.CONFLICTING if bull+bear else TimeframeAlignmentState.NEUTRAL
    weighted=sum(results[tf].confidence_score*config.timeframe_weights[tf] for tf in ALL_TIMEFRAMES); operational=DecisionConfidenceState.INVALID if alignment is TimeframeAlignmentState.INVALID else DecisionConfidenceState.STALE if alignment is TimeframeAlignmentState.STALE else DecisionConfidenceState.CONFLICTING if alignment is TimeframeAlignmentState.CONFLICTING else DecisionConfidenceState.PROVISIONAL if any(r.confidence_state is DecisionConfidenceState.PROVISIONAL for r in results.values()) else _level(weighted,config)
    supports=tuple(x for x in (ReasonCode.ALIGNED_TREND_STRUCTURE if alignment in {TimeframeAlignmentState.FULLY_ALIGNED,TimeframeAlignmentState.MOSTLY_ALIGNED} else None,ReasonCode.CONFIRMED_TIMING if all(r.timing_gate.multiplier==ONE for r in results.values()) else None) if x); conflicts=tuple(x for x in (ReasonCode.CONFLICTING_TIMEFRAMES if alignment is TimeframeAlignmentState.CONFLICTING else None,ReasonCode.STALE_DATA if alignment is TimeframeAlignmentState.STALE else None) if x)
    return DecisionConfidenceResult(DECISION_CONFIDENCE_ENGINE_VERSION,contract.contract_version,contract.evaluated_at,direction,weighted.quantize(Decimal(".01")),operational,_level(weighted,config),alignment,ratio,bull,bear,neutral,len(usable),sum(r.timing_gate.multiplier==ONE for r in results.values()),results,supports,conflicts,(),operational not in {DecisionConfidenceState.INVALID,DecisionConfidenceState.STALE,DecisionConfidenceState.CALCULATION_ERROR},(),())
