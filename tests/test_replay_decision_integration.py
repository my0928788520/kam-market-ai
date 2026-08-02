from test_replay_evaluator_adapter import Result
from test_replay_input_contract import events, metadata
from dataclasses import replace
from kam_market_ai.replay import ReplayInputConfig, ReplayRunnerConfig, ReplayTimelineConfig, build_replay_scenario, build_replay_timeline, run_replay_timeline
from kam_market_ai.replay.evaluator import FrozenEngineBundle
from kam_market_ai.replay.evaluator_adapter import FrozenEngineEvaluatorConfig, FrozenEngineReplayEvaluator, evaluate_replay_frame

def test_phase_three_engine_evaluation_does_not_invent_decision_results():
 frame=run_replay_timeline(build_replay_timeline(build_replay_scenario(metadata(),events(),ReplayInputConfig.provisional()),ReplayTimelineConfig.provisional()),ReplayRunnerConfig.provisional()).frames[1]; frame=replace(frame,timeframe_states={tf:replace(slot,input_snapshot={"position_input":1,"trend_input":1,"structure_input":1,"timing_input":1}) for tf,slot in frame.timeframe_states.items()}); bundle=FrozenEngineBundle(*(lambda a,b:Result() for _ in range(4)),{"position":"1","trend":"1","structure":"1","timing":"1"}); value=evaluate_replay_frame(frame,FrozenEngineReplayEvaluator(bundle,FrozenEngineEvaluatorConfig.provisional())); assert value.evaluation.decision_evaluation is None
