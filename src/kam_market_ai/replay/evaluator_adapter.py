"""Fail-closed adapter over explicitly injected frozen engine callables."""
from __future__ import annotations
from dataclasses import asdict, dataclass, is_dataclass
from hashlib import sha256
import json
from typing import Any, Mapping
from .evaluation_contract import REPLAY_EVALUATION_CONTRACT_VERSION, EvaluatedReplayFrame, ReplayDecisionEvaluation, ReplayEngineEvaluation, ReplayEngineEvaluationState, ReplayEvaluationInput, ReplayEvaluationResult, ReplayReplayEvaluationState
from .evaluator import FrozenEngineBundle, ReplayEvaluator
from .decision_adapter import ReplayDecisionAdapterConfig, evaluate_existing_decision
from .decision_bundle import FrozenDecisionCallableBundle
from .frame import REPLAY_FRAME_VERSION, ReplayFrame, ReplayFrameState
from .input_contract import REPLAY_INPUT_CONTRACT_VERSION, ReplayTimeframe, ReplayUpdateState

REPLAY_EVALUATOR_ADAPTER_VERSION = "1.0"

def _hash(value: object) -> str:
    def clean(item):
        if is_dataclass(item): return clean(asdict(item))
        if isinstance(item, Mapping): return {str(getattr(key,"value",key)): clean(value) for key,value in sorted(item.items(),key=lambda pair:str(pair[0]))}
        if isinstance(item,(tuple,list)): return [clean(value) for value in item]
        return getattr(item,"value",item) if item is not None else None
    return sha256(json.dumps(clean(value),sort_keys=True,default=str,separators=(",",":")).encode("utf-8")).hexdigest()

@dataclass(frozen=True, slots=True)
class FrozenEngineEvaluatorConfig:
    evaluator_adapter_version: str = REPLAY_EVALUATOR_ADAPTER_VERSION
    supported_replay_frame_versions: frozenset[str] = frozenset({REPLAY_FRAME_VERSION})
    supported_replay_input_versions: frozenset[str] = frozenset({REPLAY_INPUT_CONTRACT_VERSION})
    required_timeframes: tuple[ReplayTimeframe,...] = (ReplayTimeframe.M15,ReplayTimeframe.M60,ReplayTimeframe.D1,ReplayTimeframe.W1)
    evaluate_boundary_frames: bool = False; evaluate_unchanged_frames: bool = True; evaluate_partial_updates: bool = True
    stop_on_engine_error: bool = True; stop_on_decision_error: bool = True; allow_partial_engine_result: bool = False
    reject_stale_frame: bool = True; reject_invalid_frame: bool = True; reject_data_gap_frame: bool = True
    maximum_warning_count: int = 64; deterministic_hash_algorithm: str = "sha256"; preserve_engine_lineage: bool = True; preserve_decision_lineage: bool = True; fail_closed_policy: str = "block"
    def __post_init__(self):
        if self.evaluator_adapter_version != REPLAY_EVALUATOR_ADAPTER_VERSION or self.required_timeframes != (ReplayTimeframe.M15,ReplayTimeframe.M60,ReplayTimeframe.D1,ReplayTimeframe.W1) or self.maximum_warning_count<=0 or self.deterministic_hash_algorithm!="sha256" or self.fail_closed_policy!="block": raise ValueError("Invalid frozen evaluator configuration")
    @classmethod
    def provisional(cls): return cls()

def replay_evaluation_input_from_frame(frame: ReplayFrame) -> ReplayEvaluationInput:
    inputs={timeframe: slot.input_snapshot for timeframe,slot in frame.timeframe_states.items()}
    return ReplayEvaluationInput(REPLAY_EVALUATION_CONTRACT_VERSION,frame.scenario_id,frame.run_id,frame.frame_id,frame.frame_sequence,frame.occurred_at,frame.evaluated_at,frame.timezone,frame.symbol,frame.market,frame.session_state,inputs,frame.source_event_id,frame.source_event_sequence,frame.frame_hash,frame.source_lineage,frame.valid,frame.warnings,frame.error_codes)

class FrozenEngineReplayEvaluator:
    """Invokes only an explicit, deterministic frozen callable bundle."""
    def __init__(self,bundle: FrozenEngineBundle,config: FrozenEngineEvaluatorConfig,decision_bundle: FrozenDecisionCallableBundle|None=None,decision_config: ReplayDecisionAdapterConfig|None=None):
        if not isinstance(bundle,FrozenEngineBundle) or not isinstance(config,FrozenEngineEvaluatorConfig): raise TypeError("Frozen engine bundle and config required")
        self.bundle,self.config,self.decision_bundle,self.decision_config=bundle,config,decision_bundle,decision_config or ReplayDecisionAdapterConfig()
    @property
    def evaluator_version(self)->str: return REPLAY_EVALUATOR_ADAPTER_VERSION
    def evaluate(self,frame_input: ReplayEvaluationInput)->ReplayEvaluationResult:
        if not isinstance(frame_input,ReplayEvaluationInput): return self._failed("input_type_mismatch",None)
        if not frame_input.valid: return self._failed("invalid_frame",frame_input)
        records=[]
        try:
            for timeframe in self.config.required_timeframes:
                payload=frame_input.timeframe_inputs.get(timeframe)
                for name in ("position","trend","structure","timing"):
                    version=self.bundle.engine_versions.get(name,"")
                    if not payload:
                        records.append(ReplayEngineEvaluation(name,version,timeframe,frame_input.frame_id,None,"",None,ReplayEngineEvaluationState.UNAVAILABLE,False,None,(),("unavailable_input",),{})); continue
                    module_input=payload.get(f"{name}_input")
                    if module_input is None:
                        records.append(ReplayEngineEvaluation(name,version,timeframe,frame_input.frame_id,None,_hash(payload),None,ReplayEngineEvaluationState.UNAVAILABLE,False,None,(),("missing_module_input",),{})); continue
                    output=getattr(self.bundle,name)(module_input,timeframe)
                    records.append(ReplayEngineEvaluation(name,version,timeframe,frame_input.frame_id,None,_hash(module_input),_hash(output),ReplayEngineEvaluationState.EVALUATED,bool(getattr(output,"valid",False)),output,tuple(getattr(output,"warnings",()))[:self.config.maximum_warning_count],tuple(getattr(output,"error_codes",())) if hasattr(output,"error_codes") else (),{"frame_hash":frame_input.frame_hash}))
        except Exception: return self._failed("engine_exception",frame_input,tuple(records))
        valid=all(record.evaluation_state is ReplayEngineEvaluationState.EVALUATED and record.valid for record in records)
        state=ReplayReplayEvaluationState.EVALUATED if valid else ReplayReplayEvaluationState.INVALID
        decision=None
        if valid and self.decision_bundle is not None:
            decision=evaluate_existing_decision(evaluation_input=frame_input,engine_evaluations=tuple(records),bundle=self.decision_bundle,config=self.decision_config)
            if not decision.valid: return self._result(frame_input,tuple(records),ReplayReplayEvaluationState.FAILED,False,decision.error_codes,decision)
        return self._result(frame_input,tuple(records),state,valid,() if valid else ("partial_engine_result",),decision)
    def _failed(self,code:str,input:ReplayEvaluationInput|None,records:tuple[ReplayEngineEvaluation,...]=())->ReplayEvaluationResult:
        return self._result(input,records,ReplayReplayEvaluationState.FAILED,False,(code,))
    def _result(self,input,records,state,valid,errors,decision=None):
        frame_id=getattr(input,"frame_id",""); frame_hash=getattr(input,"frame_hash",""); evaluated_at=getattr(input,"evaluated_at",None); identifier=sha256(f"{frame_id}|{frame_hash}|{self.evaluator_version}|{_hash(self.config)}".encode("utf-8")).hexdigest(); digest=_hash((identifier,records,errors))
        digest=_hash((identifier,records,decision,errors))
        return ReplayEvaluationResult(REPLAY_EVALUATION_CONTRACT_VERSION,REPLAY_EVALUATOR_ADAPTER_VERSION,self.evaluator_version,frame_id,frame_hash,identifier,state,evaluated_at,records,decision,digest,valid,(),tuple(errors),{})

def evaluate_replay_frame(frame: ReplayFrame,evaluator: ReplayEvaluator)->EvaluatedReplayFrame:
    if not isinstance(frame,ReplayFrame) or not callable(getattr(evaluator,"evaluate",None)) or not isinstance(getattr(evaluator,"evaluator_version",None),str):
        raise TypeError("ReplayFrame and ReplayEvaluator are required")
    evaluation=evaluator.evaluate(replay_evaluation_input_from_frame(frame)); digest=sha256(f"{frame.frame_hash}|{evaluation.evaluation_hash}".encode("utf-8")).hexdigest()
    return EvaluatedReplayFrame(frame,evaluation,digest,frame.valid and evaluation.valid,evaluation.warnings,evaluation.error_codes)
