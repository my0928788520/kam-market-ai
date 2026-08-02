"""Safe metadata loader for deterministic replay fixture documents."""
from __future__ import annotations
import json
from pathlib import Path
from typing import Any, Mapping

REPLAY_FIXTURE_VERSION = "1.0"
REPLAY_FIXTURE_NAMES = frozenset({"aligned_trend_progression", "higher_timeframe_conflict_emerges", "wait_for_candle_close", "stale_data_recovery", "market_open_to_close", "partial_timeframe_updates", "data_gap", "source_correction", "invalid_version", "timezone_mismatch"})

def load_replay_fixture(name: str, directory: Path) -> Mapping[str, Any]:
    if name not in REPLAY_FIXTURE_NAMES or "/" in name or "\\" in name or ".." in name: raise ValueError("Fixture name is not allowed")
    path = Path(directory) / f"{name}.json"
    if not path.is_file(): raise FileNotFoundError("Replay fixture is unavailable")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, Mapping) or value.get("fixture_version") != REPLAY_FIXTURE_VERSION or value.get("name") != name: raise ValueError("Invalid replay fixture metadata")
    return value
