from test_replay_input_contract import events, metadata
from kam_market_ai.replay.input_contract import ReplayInputConfig, build_replay_scenario
from kam_market_ai.replay.timeline import ReplayTimelineConfig, build_replay_timeline

def test_replay_has_no_runtime_clock_or_mutable_state_dependency():
    scenarios = [build_replay_scenario(metadata(), events(), ReplayInputConfig.provisional()) for _ in range(2)]
    assert scenarios[0] == scenarios[1]
    assert build_replay_timeline(scenarios[0], ReplayTimelineConfig.provisional()) == build_replay_timeline(scenarios[1], ReplayTimelineConfig.provisional())
