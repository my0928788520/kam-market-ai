"""Fail-closed bridge from evaluated engine slots to injected Decision APIs."""
from __future__ import annotations
from dataclasses import asdict, is_dataclass
from dataclasses import dataclass
from hashlib import sha256
import json
from typing import Mapping
from .decision_bundle import FrozenDecisionCallableBundle
from .evaluation_contract import (REPLAY_EVALUATION_CONTRACT_VERSION, ReplayDecisionEvaluation,
    ReplayEngineEvaluation, ReplayEngineEvaluationState, ReplayEvaluationInput)
from .input_contract import ReplayTimeframe

REPLAY_DECISION_ADAPTER_VERSION = "1.0"

def _hash(value: object) -> str:
    def clean(item: object):
        if is_dataclass(item): return clean(asdict(item))
        if isinstance(item, Mapping): return {str(getattr(k, "value", k)): clean(v) for k,v in sorted(item.items(), key=lambda pair: str(pair[0]))}
        if isinstance(item, (tuple, list)): return [clean(v) for v in item]
        return getattr(item, "value", item)
    return sha256(json.dumps(clean(value), sort_keys=True, default=str, separators=(",", ":")).encode()).hexdigest()

@dataclass(frozen=True, slots=True)
class ReplayDecisionAdapterConfig:
    decision_adapter_version: str = REPLAY_DECISION_ADAPTER_VERSION
    supported_evaluation_contract_versions: frozenset[str] = frozenset({REPLAY_EVALUATION_CONTRACT_VERSION})
    supported_engine_versions: frozenset[str] = frozenset({"1.0"})
    supported_decision_input_versions: frozenset[str] = frozenset({"1.0"})
    supported_confidence_versions: frozenset[str] = frozenset({"1.0"})
    supported_risk_versions: frozenset[str] = frozenset({"1.0"})
    supported_next_step_versions: frozenset[str] = frozenset({"1.0"})
    required_timeframes: tuple[ReplayTimeframe,...] = (ReplayTimeframe.M15, ReplayTimeframe.M60, ReplayTimeframe.D1, ReplayTimeframe.W1)
    required_modules: tuple[str,...] = ("position", "trend", "structure", "timing")
    reject_partial_engine_evaluation: bool = True; reject_invalid_engine_evaluation: bool = True; reject_stale_engine_evaluation: bool = True; reject_unavailable_engine_evaluation: bool = True
    stop_on_decision_input_error: bool = True; stop_on_confidence_error: bool = True; stop_on_risk_error: bool = True
    stop_on_next_step_error: bool = True; maximum_warning_count: int = 64; deterministic_hash_algorithm: str = "sha256"
    preserve_engine_lineage: bool = True; preserve_decision_lineage: bool = True; fail_closed_policy: str = "block"
    def __post_init__(self):
        if self.decision_adapter_version != REPLAY_DECISION_ADAPTER_VERSION or self.deterministic_hash_algorithm != "sha256" or self.fail_closed_policy != "block" or self.maximum_warning_count <= 0:
            raise ValueError("Invalid frozen Decision adapter configuration")

def _failure(input: ReplayEvaluationInput, bundle: FrozenDecisionCallableBundle | None, code: str) -> ReplayDecisionEvaluation:
    return ReplayDecisionEvaluation(getattr(bundle,"decision_input_version",None),getattr(bundle,"confidence_version",None),getattr(bundle,"risk_version",None),getattr(bundle,"next_step_version",None),input.frame_id,input.frame_hash,input.evaluated_at,None,None,None,None,False,None,None,None,None,(),(code,),{"decision_adapter_version": REPLAY_DECISION_ADAPTER_VERSION})

def build_existing_decision_input_from_replay(*, evaluation_input: ReplayEvaluationInput, engine_evaluations: tuple[ReplayEngineEvaluation,...], bundle: FrozenDecisionCallableBundle, config: ReplayDecisionAdapterConfig) -> object:
    slots = {(item.timeframe, item.engine_name): item for item in engine_evaluations}
    expected = [(timeframe, module) for timeframe in config.required_timeframes for module in config.required_modules]
    if len(engine_evaluations) != len(expected) or any(key not in slots for key in expected): raise ValueError("incomplete_engine_evaluation")
    if any(item.evaluation_state is not ReplayEngineEvaluationState.EVALUATED or not item.valid or item.source_frame_id != evaluation_input.frame_id for item in slots.values()): raise ValueError("invalid_engine_evaluation")
    if any(item.engine_version not in config.supported_engine_versions for item in slots.values()): raise ValueError("unsupported_engine_version")
    grouped = {module: {timeframe: slots[(timeframe,module)].output for timeframe in config.required_timeframes} for module in config.required_modules}
    return bundle.decision_input_builder(position_results_by_timeframe=grouped["position"], trend_results_by_timeframe=grouped["trend"], structure_results_by_timeframe=grouped["structure"], timing_results_by_timeframe=grouped["timing"], evaluated_at=evaluation_input.evaluated_at)

def evaluate_existing_decision(*, evaluation_input: ReplayEvaluationInput, engine_evaluations: tuple[ReplayEngineEvaluation,...], bundle: FrozenDecisionCallableBundle, config: ReplayDecisionAdapterConfig) -> ReplayDecisionEvaluation:
    if not isinstance(bundle, FrozenDecisionCallableBundle): return _failure(evaluation_input, None, "decision_bundle_type_mismatch")
    if evaluation_input.evaluation_contract_version not in config.supported_evaluation_contract_versions: return _failure(evaluation_input,bundle,"unsupported_evaluation_contract")
    try:
        decision_input = build_existing_decision_input_from_replay(evaluation_input=evaluation_input, engine_evaluations=engine_evaluations, bundle=bundle, config=config)
        if getattr(decision_input,"contract_version",None) != bundle.decision_input_version or bundle.decision_input_version not in config.supported_decision_input_versions: return _failure(evaluation_input,bundle,"decision_input_version_mismatch")
        confidence = bundle.confidence_callable(decision_input)
        if getattr(confidence,"engine_version",getattr(confidence,"confidence_version",None)) != bundle.confidence_version or bundle.confidence_version not in config.supported_confidence_versions: return _failure(evaluation_input,bundle,"confidence_version_mismatch")
        risk = bundle.risk_callable(decision_input, confidence)
        if getattr(risk,"engine_version",getattr(risk,"risk_version",None)) != bundle.risk_version or bundle.risk_version not in config.supported_risk_versions: return _failure(evaluation_input,bundle,"risk_version_mismatch")
        next_step = bundle.next_step_callable(decision_input, confidence, risk)
        if getattr(next_step,"engine_version",getattr(next_step,"next_step_version",None)) != bundle.next_step_version or bundle.next_step_version not in config.supported_next_step_versions: return _failure(evaluation_input,bundle,"next_step_version_mismatch")
        objects=(decision_input,confidence,risk,next_step)
        if not all(bool(getattr(value,"valid",False)) for value in objects): return _failure(evaluation_input,bundle,"invalid_decision_result")
        warnings=tuple(item for value in objects for item in getattr(value,"warnings",()))[:config.maximum_warning_count]
        return ReplayDecisionEvaluation(bundle.decision_input_version,bundle.confidence_version,bundle.risk_version,bundle.next_step_version,evaluation_input.frame_id,evaluation_input.frame_hash,evaluation_input.evaluated_at,*(_hash(value) for value in objects),True,*objects,warnings,(),{"decision_adapter_version":REPLAY_DECISION_ADAPTER_VERSION,"source_frame_hash":evaluation_input.frame_hash,**dict(bundle.lineage)})
    except ValueError as exc:
        return _failure(evaluation_input,bundle,str(exc))
    except Exception:
        return _failure(evaluation_input,bundle,"decision_callable_exception")
