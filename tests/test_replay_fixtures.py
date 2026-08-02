from pathlib import Path
import pytest
from kam_market_ai.replay.fixtures import REPLAY_FIXTURE_NAMES, load_replay_fixture

def test_fixture_loader_uses_only_fixed_safe_names():
    directory = Path(__file__).parent / "fixtures" / "replay"
    assert set(path.stem for path in directory.glob("*.json")) == set(REPLAY_FIXTURE_NAMES)
    assert load_replay_fixture("data_gap", directory)["name"] == "data_gap"
    with pytest.raises(ValueError): load_replay_fixture("../data_gap", directory)
