from test_replay_input_contract import END, START, metadata
from kam_market_ai.replay import ReplayEvent, ReplayEventType, ReplayInputConfig, ReplayRunnerConfig, ReplaySessionState, ReplayTimelineConfig, build_replay_scenario, build_replay_timeline, deterministic_event_id, run_replay_timeline

def test_source_correction_is_a_deterministic_corrected_frame():
    values=[]
    for seq, (kind, at) in enumerate(((ReplayEventType.SCENARIO_START,START),(ReplayEventType.SOURCE_CORRECTION,START),(ReplayEventType.SCENARIO_END,END)),1): values.append(ReplayEvent(deterministic_event_id("correction",seq,at,kind),seq,kind,at,at,"Asia/Taipei","MTX","TW",ReplaySessionState.OPEN,(),{},"historical_fixture","1.0",{},"available",True))
    timeline=build_replay_timeline(build_replay_scenario(metadata(),tuple(values),ReplayInputConfig.provisional()),ReplayTimelineConfig.provisional()); run=run_replay_timeline(timeline,ReplayRunnerConfig.provisional())
    assert run.valid and run.frames[1].frame_state.value == "corrected"
