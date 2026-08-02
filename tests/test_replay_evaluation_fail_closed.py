from test_replay_input_contract import events, metadata
from kam_market_ai.replay import ReplayInputConfig, ReplayRunnerConfig, ReplayTimelineConfig, build_replay_scenario, build_replay_timeline, run_replay_timeline
from kam_market_ai.replay.evaluator import FrozenEngineBundle
from kam_market_ai.replay.evaluator_adapter import FrozenEngineEvaluatorConfig, FrozenEngineReplayEvaluator, evaluate_replay_frame
def test_missing_module_inputs_fail_closed_without_exception_leak():
 frame=run_replay_timeline(build_replay_timeline(build_replay_scenario(metadata(),events(),ReplayInputConfig.provisional()),ReplayTimelineConfig.provisional()),ReplayRunnerConfig.provisional()).frames[1]; bundle=FrozenEngineBundle(*(lambda a,b:None for _ in range(4)),{"position":"1","trend":"1","structure":"1","timing":"1"}); assert not evaluate_replay_frame(frame,FrozenEngineReplayEvaluator(bundle,FrozenEngineEvaluatorConfig.provisional())).valid
