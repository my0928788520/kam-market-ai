from dataclasses import dataclass, replace
from kam_market_ai.replay.decision_adapter import ReplayDecisionAdapterConfig
from kam_market_ai.replay.decision_bundle import FrozenDecisionCallableBundle
from kam_market_ai.replay.evaluator import FrozenEngineBundle
from kam_market_ai.replay.evaluator_adapter import FrozenEngineEvaluatorConfig, FrozenEngineReplayEvaluator, evaluate_replay_frame
from test_replay_input_contract import events, metadata
from kam_market_ai.replay import ReplayInputConfig, ReplayRunnerConfig, ReplayTimelineConfig, build_replay_scenario, build_replay_timeline, run_replay_timeline

@dataclass(frozen=True)
class _Engine: valid: bool=True; warnings: tuple=(); error_codes: tuple=()
@dataclass(frozen=True)
class _Decision: contract_version: str="1.0"; valid: bool=True; warnings: tuple=()
@dataclass(frozen=True)
class _Confidence: engine_version: str="1.0"; valid: bool=True; warnings: tuple=()
@dataclass(frozen=True)
class _Risk: engine_version: str="1.0"; valid: bool=True; warnings: tuple=()
@dataclass(frozen=True)
class _Next: engine_version: str="1.0"; valid: bool=True; warnings: tuple=()

def _frame():
    frame=run_replay_timeline(build_replay_timeline(build_replay_scenario(metadata(),events(),ReplayInputConfig.provisional()),ReplayTimelineConfig.provisional()),ReplayRunnerConfig.provisional()).frames[1]
    return replace(frame,timeframe_states={tf:replace(slot,input_snapshot={f"{name}_input": 1 for name in ("position","trend","structure","timing")}) for tf,slot in frame.timeframe_states.items()})

def _bundle():
    return FrozenDecisionCallableBundle("1.0",lambda **_:_Decision(),lambda _: _Confidence(),lambda *_:_Risk(),lambda *_:_Next(),"1.0","1.0","1.0","1.0",{"source":"test"})

def _engine():
    return FrozenEngineBundle(*(lambda *_:_Engine() for _ in range(4)),{"position":"1.0","trend":"1.0","structure":"1.0","timing":"1.0"})

def test_full_bundle_attaches_deterministic_decision_evaluation():
    evaluator=FrozenEngineReplayEvaluator(_engine(),FrozenEngineEvaluatorConfig(),_bundle(),ReplayDecisionAdapterConfig())
    first=evaluate_replay_frame(_frame(),evaluator); second=evaluate_replay_frame(_frame(),evaluator)
    assert first.valid and first.evaluation.decision_evaluation is not None
    assert first.evaluation.evaluation_hash == second.evaluation.evaluation_hash

def test_decision_failure_is_fail_closed_without_changing_engine_only_mode():
    bad=FrozenDecisionCallableBundle("1.0",lambda **_:_Decision(),lambda _: (_ for _ in ()).throw(RuntimeError()),lambda *_:_Risk(),lambda *_:_Next(),"1.0","1.0","1.0","1.0",{})
    failed=evaluate_replay_frame(_frame(),FrozenEngineReplayEvaluator(_engine(),FrozenEngineEvaluatorConfig(),bad,ReplayDecisionAdapterConfig()))
    engine_only=evaluate_replay_frame(_frame(),FrozenEngineReplayEvaluator(_engine(),FrozenEngineEvaluatorConfig()))
    assert not failed.valid and failed.evaluation.decision_evaluation.error_codes == ("decision_callable_exception",)
    assert engine_only.valid and engine_only.evaluation.decision_evaluation is None
