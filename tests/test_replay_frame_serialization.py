import json
from test_replay_input_contract import events, metadata
from kam_market_ai.replay import ReplayFrameSerializationConfig, ReplayInputConfig, ReplayRunnerConfig, ReplayTimelineConfig, build_replay_scenario, build_replay_timeline, replay_frame_payload_to_canonical_json, run_replay_timeline, serialize_replay_run

def test_frame_run_serialization_is_deterministic_json():
    timeline = build_replay_timeline(build_replay_scenario(metadata(), events(), ReplayInputConfig.provisional()), ReplayTimelineConfig.provisional())
    run = run_replay_timeline(timeline, ReplayRunnerConfig.provisional()); config = ReplayFrameSerializationConfig.provisional()
    text = replay_frame_payload_to_canonical_json(serialize_replay_run(run, config), config)
    assert json.loads(text)["payload_type"] == "replay_run" and "not_evaluated" in text
