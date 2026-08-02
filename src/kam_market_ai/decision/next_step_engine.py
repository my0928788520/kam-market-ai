"""Read-only observation and verification resolver; it never produces trade instructions."""
from __future__ import annotations
from dataclasses import dataclass
from enum import StrEnum
from typing import Mapping
from ..analysis.position_engine import ALL_TIMEFRAMES, PositionTimeframe
from .decision_contract import DECISION_INPUT_CONTRACT_VERSION, DecisionInputContract, DecisionInputStatus, NormalizedModuleState
from .decision_confidence import DECISION_CONFIDENCE_ENGINE_VERSION, DecisionConfidenceResult
from .risk_engine import RISK_ENGINE_VERSION, RiskOperationalState, RiskResult
NEXT_STEP_ENGINE_VERSION="1.0"
class NextStepType(StrEnum): MAINTAIN_OBSERVATION="maintain_observation"; WAIT_FOR_CANDLE_CLOSE="wait_for_candle_close"; WAIT_FOR_CONFIRMATION="wait_for_confirmation"; VERIFY_BREAKOUT="verify_breakout"; VERIFY_BREAKDOWN="verify_breakdown"; VERIFY_RETEST="verify_retest"; REVIEW_TREND="review_trend"; REVIEW_STRUCTURE="review_structure"; PAUSE_DECISION="pause_decision"; MARKET_CLOSED_WAIT="market_closed_wait"; INSUFFICIENT_DATA_WAIT="insufficient_data_wait"; NO_ACTION_REQUIRED="no_action_required"; UNAVAILABLE="unavailable"; INVALID="invalid"; CALCULATION_ERROR="calculation_error"
class NextStepOperationalState(StrEnum): VALID="valid"; PROVISIONAL="provisional"; WAITING="waiting"; VERIFICATION_REQUIRED="verification_required"; REVIEW_REQUIRED="review_required"; BLOCKED="blocked"; STALE="stale"; INSUFFICIENT="insufficient"; UNAVAILABLE="unavailable"; INVALID="invalid"; CALCULATION_ERROR="calculation_error"
class NextStepPriority(StrEnum): CRITICAL="critical"; HIGH="high"; MEDIUM="medium"; LOW="low"; INFO="info"
class NextStepReasonCode(StrEnum): INVALID_SOURCE="invalid_source"; STALE_SOURCE="stale_source"; HIGHER_TIMEFRAME_CONFLICT="higher_timeframe_conflict"; MODULE_CONFLICT="module_conflict"; WAIT_FOR_CLOSE="wait_for_close"; PROVISIONAL_TIMING="provisional_timing"; STRUCTURE_REVIEW="structure_review"; TREND_REVIEW="trend_review"; INSUFFICIENT_DATA="insufficient_data"; MAINTAIN_OBSERVATION="maintain_observation"
@dataclass(frozen=True,slots=True)
class NextStepEngineConfig:
 supported_contract_versions:frozenset[str]=frozenset({DECISION_INPUT_CONTRACT_VERSION}); supported_confidence_versions:frozenset[str]=frozenset({DECISION_CONFIDENCE_ENGINE_VERSION}); supported_risk_versions:frozenset[str]=frozenset({RISK_ENGINE_VERSION}); priority_order:tuple[NextStepPriority,...]=(NextStepPriority.CRITICAL,NextStepPriority.HIGH,NextStepPriority.MEDIUM,NextStepPriority.LOW,NextStepPriority.INFO); allow_no_action_required:bool=False
 def __post_init__(self):
  if not self.supported_contract_versions or not self.supported_confidence_versions or not self.supported_risk_versions or len(set(self.priority_order))!=5: raise ValueError("Versions and priority order must be complete.")
 @classmethod
 def provisional(cls)->"NextStepEngineConfig":return cls()
@dataclass(frozen=True,slots=True)
class TimeframeNextStep: timeframe:PositionTimeframe; step_type:NextStepType; operational_state:NextStepOperationalState; priority:NextStepPriority; reason_codes:tuple[NextStepReasonCode,...]; reassessment_triggers:tuple[str,...]; review_modules:tuple[str,...]; supporting_factors:tuple[str,...]; valid:bool; warnings:tuple[str,...]; error_codes:tuple[str,...]
@dataclass(frozen=True,slots=True)
class NextStepResult: engine_version:str; contract_version:str; confidence_engine_version:str; risk_engine_version:str; evaluated_at:object; next_step:NextStepType; operational_state:NextStepOperationalState; priority:NextStepPriority; reason_codes:tuple[NextStepReasonCode,...]; timeframe_steps:Mapping[PositionTimeframe,TimeframeNextStep]; reassessment_triggers:tuple[str,...]; review_modules:tuple[str,...]; supporting_factors:tuple[str,...]; valid:bool; warnings:tuple[str,...]; error_codes:tuple[str,...]
def _invalid(c,co,r,code):return NextStepResult(NEXT_STEP_ENGINE_VERSION,getattr(c,"contract_version","?"),getattr(co,"engine_version","?"),getattr(r,"engine_version","?"),getattr(c,"evaluated_at",None),NextStepType.INVALID,NextStepOperationalState.INVALID,NextStepPriority.CRITICAL,(NextStepReasonCode.INVALID_SOURCE,),{},(),(),(),False,(),(code,))
def _resolve(frame):
 if frame.input_status is DecisionInputStatus.INVALID:return NextStepType.INVALID,NextStepOperationalState.INVALID,NextStepPriority.CRITICAL,(NextStepReasonCode.INVALID_SOURCE,)
 if frame.input_status is DecisionInputStatus.STALE:return NextStepType.PAUSE_DECISION,NextStepOperationalState.STALE,NextStepPriority.CRITICAL,(NextStepReasonCode.STALE_SOURCE,)
 if frame.timing.normalized_state is NormalizedModuleState.WAITING:return NextStepType.WAIT_FOR_CANDLE_CLOSE,NextStepOperationalState.WAITING,NextStepPriority.HIGH,(NextStepReasonCode.WAIT_FOR_CLOSE,)
 if frame.timing.normalized_state is NormalizedModuleState.PROVISIONAL:return NextStepType.WAIT_FOR_CONFIRMATION,NextStepOperationalState.PROVISIONAL,NextStepPriority.MEDIUM,(NextStepReasonCode.PROVISIONAL_TIMING,)
 if frame.trend.normalized_state is NormalizedModuleState.AMBIGUOUS:return NextStepType.REVIEW_TREND,NextStepOperationalState.REVIEW_REQUIRED,NextStepPriority.HIGH,(NextStepReasonCode.TREND_REVIEW,)
 if frame.structure.normalized_state in {NormalizedModuleState.PROVISIONAL,NormalizedModuleState.CONFLICTING}:return NextStepType.REVIEW_STRUCTURE,NextStepOperationalState.REVIEW_REQUIRED,NextStepPriority.HIGH,(NextStepReasonCode.STRUCTURE_REVIEW,)
 return NextStepType.MAINTAIN_OBSERVATION,NextStepOperationalState.VALID,NextStepPriority.INFO,(NextStepReasonCode.MAINTAIN_OBSERVATION,)
def evaluate_next_step(contract:DecisionInputContract,confidence:DecisionConfidenceResult,risk:RiskResult,config:NextStepEngineConfig)->NextStepResult:
 if not isinstance(contract,DecisionInputContract) or not isinstance(confidence,DecisionConfidenceResult) or not isinstance(risk,RiskResult):raise TypeError("contract, confidence and risk must use supported types")
 if contract.contract_version not in config.supported_contract_versions or confidence.engine_version not in config.supported_confidence_versions or risk.engine_version not in config.supported_risk_versions or contract.evaluated_at!=confidence.evaluated_at or contract.evaluated_at!=risk.evaluated_at:return _invalid(contract,confidence,risk,"source_mismatch")
 steps={}
 for tf in ALL_TIMEFRAMES:
  frame=contract.timeframes.get(tf)
  if frame is None:steps[tf]=TimeframeNextStep(tf,NextStepType.UNAVAILABLE,NextStepOperationalState.UNAVAILABLE,NextStepPriority.HIGH,(NextStepReasonCode.INSUFFICIENT_DATA,),(),(),(),False,(),("missing_timeframe",));continue
  typ,state,priority,reasons=_resolve(frame);steps[tf]=TimeframeNextStep(tf,typ,state,priority,reasons,("reassess_on_next_completed_candle",),(),(),state is NextStepOperationalState.VALID,frame.warnings,frame.error_codes)
 if risk.operational_state is RiskOperationalState.INVALID:return _invalid(contract,confidence,risk,"invalid_risk")
 if risk.operational_state is RiskOperationalState.STALE:overall=(NextStepType.PAUSE_DECISION,NextStepOperationalState.STALE,NextStepPriority.CRITICAL,(NextStepReasonCode.STALE_SOURCE,))
 elif risk.higher_timeframe_conflict_risk>0:overall=(NextStepType.PAUSE_DECISION,NextStepOperationalState.BLOCKED,NextStepPriority.CRITICAL,(NextStepReasonCode.HIGHER_TIMEFRAME_CONFLICT,))
 elif risk.timeframe_conflict_risk>0:overall=(NextStepType.PAUSE_DECISION,NextStepOperationalState.BLOCKED,NextStepPriority.HIGH,(NextStepReasonCode.MODULE_CONFLICT,))
 else:overall=min(((x.step_type,x.operational_state,x.priority,x.reason_codes) for x in steps.values()),key=lambda x:config.priority_order.index(x[2]))
 typ,state,priority,reasons=overall;return NextStepResult(NEXT_STEP_ENGINE_VERSION,contract.contract_version,confidence.engine_version,risk.engine_version,contract.evaluated_at,typ,state,priority,reasons,steps,("reassess_on_next_completed_candle",),(),(),state is NextStepOperationalState.VALID,(),())
