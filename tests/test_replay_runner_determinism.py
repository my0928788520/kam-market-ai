from test_replay_input_contract import events, metadata
from kam_market_ai.replay import ReplayInputConfig, ReplayRunnerConfig, ReplayTimelineConfig, build_replay_scenario, build_replay_timeline, run_replay_timeline

def test_runner_and_frame_hashes_are_repeatable():
    timeline = build_replay_timeline(build_replay_scenario(metadata(), events(), ReplayInputConfig.provisional()), ReplayTimelineConfig.provisional())
    first, second = run_replay_timeline(timeline, ReplayRunnerConfig.provisional()), run_replay_timeline(timeline, ReplayRunnerConfig.provisional())
    assert first.run_id == second.run_id and first.run_hash == second.run_hash and first.frames == second.frames
