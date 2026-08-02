from dataclasses import dataclass, replace
from test_replay_input_contract import events, metadata
from kam_market_ai.replay import ReplayFrameTimeframeState, ReplayInputConfig, ReplayRunnerConfig, ReplayTimelineConfig, ReplayUpdateState, ReplayCandleState, build_replay_scenario, build_replay_timeline, run_replay_timeline
from kam_market_ai.replay.evaluator import FrozenEngineBundle
from kam_market_ai.replay.evaluator_adapter import FrozenEngineEvaluatorConfig, FrozenEngineReplayEvaluator, evaluate_replay_frame

@dataclass(frozen=True)
class Result: valid: bool=True; warnings: tuple=(); error_codes: tuple=()
def test_injected_frozen_bundle_evaluates_fixed_engine_slots_deterministically():
    frame=run_replay_timeline(build_replay_timeline(build_replay_scenario(metadata(),events(),ReplayInputConfig.provisional()),ReplayTimelineConfig.provisional()),ReplayRunnerConfig.provisional()).frames[1]
    slots={timeframe:replace(slot,input_snapshot={"position_input":1,"trend_input":1,"structure_input":1,"timing_input":1}) for timeframe,slot in frame.timeframe_states.items()}
    frame=replace(frame,timeframe_states=slots); bundle=FrozenEngineBundle(*(lambda value,timeframe:Result() for _ in range(4)),{"position":"1.0","trend":"1.0","structure":"1.0","timing":"1.0"})
    evaluated=evaluate_replay_frame(frame,FrozenEngineReplayEvaluator(bundle,FrozenEngineEvaluatorConfig.provisional()))
    assert evaluated.valid and len(evaluated.evaluation.engine_evaluations)==16 and evaluated.evaluation.evaluation_state.value=="evaluated"
