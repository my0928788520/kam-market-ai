from test_replay_evaluator_adapter import Result
from test_replay_input_contract import events, metadata
from dataclasses import replace
from kam_market_ai.replay import ReplayInputConfig, ReplayRunnerConfig, ReplayTimelineConfig, build_replay_scenario, build_replay_timeline, run_replay_timeline
from kam_market_ai.replay.evaluator import FrozenEngineBundle
from kam_market_ai.replay.evaluator_adapter import FrozenEngineEvaluatorConfig, FrozenEngineReplayEvaluator, evaluate_replay_frame
from kam_market_ai.replay.evaluation_serialization import replay_evaluation_to_canonical_json, serialize_replay_evaluation
def test_evaluation_serialization_is_deterministic():
 frame=run_replay_timeline(build_replay_timeline(build_replay_scenario(metadata(),events(),ReplayInputConfig.provisional()),ReplayTimelineConfig.provisional()),ReplayRunnerConfig.provisional()).frames[1]; frame=replace(frame,timeframe_states={tf:replace(slot,input_snapshot={"position_input":1,"trend_input":1,"structure_input":1,"timing_input":1}) for tf,slot in frame.timeframe_states.items()}); bundle=FrozenEngineBundle(*(lambda a,b:Result() for _ in range(4)),{"position":"1","trend":"1","structure":"1","timing":"1"}); value=evaluate_replay_frame(frame,FrozenEngineReplayEvaluator(bundle,FrozenEngineEvaluatorConfig.provisional())); assert replay_evaluation_to_canonical_json(serialize_replay_evaluation(value))==replay_evaluation_to_canonical_json(serialize_replay_evaluation(value))
