from dataclasses import replace
from test_replay_input_contract import events, metadata
from kam_market_ai.replay import ReplayFrameTimeframeState, ReplayInputConfig, ReplayRunnerConfig, ReplayTimelineConfig, ReplayUpdateState, ReplayCandleState, build_replay_scenario, build_replay_timeline, run_replay_timeline
from kam_market_ai.replay.evaluator_adapter import replay_evaluation_input_from_frame

def test_evaluation_input_is_derived_only_from_frame_contract():
    frame=run_replay_timeline(build_replay_timeline(build_replay_scenario(metadata(),events(),ReplayInputConfig.provisional()),ReplayTimelineConfig.provisional()),ReplayRunnerConfig.provisional()).frames[1]
    value=replay_evaluation_input_from_frame(frame)
    assert value.frame_id==frame.frame_id and len(value.timeframe_inputs)==4 and value.evaluation_contract_version=="1.0"
