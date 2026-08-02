from pathlib import Path
import pytest
from kam_market_ai.replay.fixtures import load_replay_fixture

def test_fixture_loader_rejects_path_traversal_and_arbitrary_file_names():
    directory = Path(__file__).parent / "fixtures" / "replay"
    for name in ("..\\data_gap", "../../etc/passwd", "data_gap.json", "C:\\temp"):
        with pytest.raises(ValueError): load_replay_fixture(name, directory)
