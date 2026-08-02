from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from kam_market_ai.replay.input_contract import ReplayEvent, ReplayEventType, ReplayInputConfig, ReplaySessionState, build_replay_scenario, deterministic_event_id

TZ = ZoneInfo("Asia/Taipei"); START = datetime(2026, 1, 2, 9, tzinfo=TZ); END = START + timedelta(hours=1)

def events():
    scenario = "seed"
    values = []
    for sequence, (kind, at) in enumerate(((ReplayEventType.SCENARIO_START, START), (ReplayEventType.TIMEFRAME_UPDATE, START + timedelta(minutes=15)), (ReplayEventType.SCENARIO_END, END)), 1):
        values.append(ReplayEvent(deterministic_event_id(scenario, sequence, at, kind), sequence, kind, at, at, "Asia/Taipei", "MTX", "TW", ReplaySessionState.OPEN, (), {}, "historical_fixture", "1.0", {}, "available", True))
    return tuple(values)

def metadata(**changes):
    value = {"name":"sample","symbol":"MTX","market":"TW","timezone":"Asia/Taipei","start_at":START,"end_at":END,"source_type":"historical_fixture","source_version":"1.0","session":"open"}; value.update(changes); return value

def test_scenario_and_event_ids_are_deterministic():
    scenario = build_replay_scenario(metadata(), events(), ReplayInputConfig.provisional())
    assert scenario.valid and scenario.scenario_id == build_replay_scenario(metadata(), events(), ReplayInputConfig.provisional()).scenario_id
    assert scenario.expected_event_count == 3

def test_invalid_version_and_timezone_fail_closed():
    assert not build_replay_scenario(metadata(replay_input_version="2.0"), events(), ReplayInputConfig.provisional()).valid
    assert not build_replay_scenario(metadata(timezone="UTC"), events(), ReplayInputConfig.provisional()).valid
