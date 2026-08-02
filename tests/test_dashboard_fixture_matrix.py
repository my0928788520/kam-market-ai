from pathlib import Path
import json

from kam_market_ai.dashboard.wsgi_adapter import DEFAULT_FIXTURE_WHITELIST


def test_committed_fixture_matrix_is_whitelisted_and_has_stable_metadata():
    directory = Path(__file__).parent / "fixtures" / "dashboard"
    names = {path.stem for path in directory.glob("*.json")}
    assert names == set(DEFAULT_FIXTURE_WHITELIST)
    for path in directory.glob("*.json"):
        value = json.loads(path.read_text(encoding="utf-8"))
        assert value["fixture_version"] == "1.0" and value["scenario"] == path.stem
