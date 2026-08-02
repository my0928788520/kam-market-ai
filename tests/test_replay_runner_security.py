import pytest
from test_replay_input_contract import events, metadata
from kam_market_ai.replay import ReplayInputConfig, ReplayRunnerConfig, ReplayTimelineConfig, build_replay_scenario, build_replay_timeline, iter_replay_frames

def test_phase_two_rejects_injected_evaluator_execution():
    timeline=build_replay_timeline(build_replay_scenario(metadata(),events(),ReplayInputConfig.provisional()),ReplayTimelineConfig.provisional())
    with pytest.raises(ValueError): tuple(iter_replay_frames(timeline,ReplayRunnerConfig.provisional(),lambda frame: frame))
