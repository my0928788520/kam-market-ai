from test_replay_input_contract import END, START, TZ, metadata
from kam_market_ai.replay import ReplayEvent, ReplayEventType, ReplayInputConfig, ReplayRunnerConfig, ReplaySessionState, ReplayTimelineConfig, build_replay_scenario, build_replay_timeline, deterministic_event_id, run_replay_timeline

def test_data_gap_is_emitted_then_blocks_by_default():
    values=[]
    for seq, (kind, at) in enumerate(((ReplayEventType.SCENARIO_START,START),(ReplayEventType.DATA_GAP,START),(ReplayEventType.SCENARIO_END,END)),1): values.append(ReplayEvent(deterministic_event_id("gap",seq,at,kind),seq,kind,at,at,"Asia/Taipei","MTX","TW",ReplaySessionState.OPEN,(),{},"historical_fixture","1.0",{},"available",True))
    timeline=build_replay_timeline(build_replay_scenario(metadata(),tuple(values),ReplayInputConfig.provisional()),ReplayTimelineConfig.provisional()); run=run_replay_timeline(timeline,ReplayRunnerConfig.provisional())
    assert not run.valid and run.completion_state == "blocked" and run.frames[-1].frame_state.value == "data_gap"
