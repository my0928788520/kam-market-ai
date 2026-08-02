from test_replay_input_contract import events, metadata
from kam_market_ai.replay import ReplayInputConfig, ReplayRunnerConfig, ReplayTimelineConfig, build_replay_scenario, build_replay_timeline, run_replay_timeline

def test_frames_have_all_slots_and_carry_forward_lineage():
    timeline = build_replay_timeline(build_replay_scenario(metadata(), events(), ReplayInputConfig.provisional()), ReplayTimelineConfig.provisional())
    frames = run_replay_timeline(timeline, ReplayRunnerConfig.provisional()).frames
    assert all(len(frame.timeframe_states) == 4 for frame in frames)
    assert frames[1].previous_frame_id == frames[0].frame_id
    assert frames[1].previous_frame_hash == frames[0].frame_hash
