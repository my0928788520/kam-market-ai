import json
from test_replay_input_contract import events, metadata
from kam_market_ai.replay.input_contract import ReplayInputConfig, build_replay_scenario
from kam_market_ai.replay.serialization import ReplaySerializationConfig, replay_payload_to_canonical_json, serialize_replay_scenario

def test_canonical_serialization_is_json_safe_and_repeatable():
    scenario = build_replay_scenario(metadata(), events(), ReplayInputConfig.provisional()); config = ReplaySerializationConfig.provisional()
    text = replay_payload_to_canonical_json(serialize_replay_scenario(scenario, config), config)
    assert json.loads(text)["payload_type"] == "replay_scenario" and text == replay_payload_to_canonical_json(serialize_replay_scenario(scenario, config), config)
