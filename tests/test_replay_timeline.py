from test_replay_input_contract import events, metadata
from kam_market_ai.replay.input_contract import ReplayInputConfig, build_replay_scenario
from kam_market_ai.replay.timeline import ReplayTimelineConfig, build_replay_timeline

def test_timeline_is_ordered_and_hash_deterministic():
    scenario = build_replay_scenario(metadata(), events(), ReplayInputConfig.provisional())
    first = build_replay_timeline(scenario, ReplayTimelineConfig.provisional())
    second = build_replay_timeline(scenario, ReplayTimelineConfig.provisional())
    assert first.valid and first.deterministic_hash == second.deterministic_hash
    assert [event.sequence for event in first.events] == [1, 2, 3]
