from test_replay_input_contract import events, metadata
from kam_market_ai.replay import ReplayInputConfig, ReplayRunnerConfig, ReplayTimelineConfig, build_replay_scenario, build_replay_timeline, run_replay_timeline

def test_static_input_to_timeline_to_runner_frame_sequence():
    scenario=build_replay_scenario(metadata(),events(),ReplayInputConfig.provisional()); timeline=build_replay_timeline(scenario,ReplayTimelineConfig.provisional()); run=run_replay_timeline(timeline,ReplayRunnerConfig.provisional())
    assert scenario.valid and timeline.valid and run.valid and [frame.frame_sequence for frame in run.frames] == [1,2,3]
