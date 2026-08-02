from datetime import UTC, datetime, timedelta
import inspect
import json

import pytest

from kam_market_ai.market_data import pipeline_cli
from kam_market_ai.market_data.pipeline_cli import (
    OFFLINE_RESEARCH_PIPELINE_CLI_VERSION,
    build_offline_pipeline_output,
    build_parser,
    main,
)


NOW = datetime(2026, 8, 10, 10, tzinfo=UTC)


def row(instrument="MTX", record_id="record-1"):
    return {"instrument": instrument, "timeframe": "15m", "opened_at": (NOW - timedelta(minutes=15)).isoformat(), "closed_at": NOW.isoformat(), "open": "100", "high": "102", "low": "99", "close": "101", "volume": "10", "source_record_id": record_id, "closed": True}


def arguments(path, source):
    return ["--source", source, "--input", str(path), "--provider-id", "cli-fixture", "--dataset-id", "cli-dataset", "--instruments", "MTX", "--timeframe", "15m", "--start-at", (NOW - timedelta(hours=1)).isoformat(), "--end-at", (NOW + timedelta(hours=1)).isoformat(), "--as-of", (NOW + timedelta(hours=1)).isoformat(), "--captured-at", NOW.isoformat(), "--batch-size", "1"]


@pytest.mark.parametrize("source", ["replay", "fixture", "json", "csv"])
def test_cli_supports_all_explicit_offline_source_encodings(tmp_path, source):
    path = tmp_path / f"dataset.{source}"
    if source == "csv":
        item = row(); path.write_text(",".join(item) + "\n" + ",".join(str(value).lower() if isinstance(value, bool) else str(value) for value in item.values()) + "\n", encoding="utf-8")
    else:
        path.write_text(json.dumps([row()]), encoding="utf-8")
    output = build_offline_pipeline_output(build_parser().parse_args(arguments(path, source)))
    payload = json.loads(output)
    assert payload["pipeline"]["scan_status"] == "completed"
    assert payload["dashboard_projection"]["summary"]["completed_instrument_count"] == 1


def test_cli_output_is_deterministic_and_compact(tmp_path):
    path = tmp_path / "fixture.json"; path.write_text(json.dumps([row()]), encoding="utf-8")
    args = build_parser().parse_args(arguments(path, "fixture"))
    first = build_offline_pipeline_output(args)
    assert first == build_offline_pipeline_output(args)
    assert "\n" not in first and json.loads(first)["cli_version"] == OFFLINE_RESEARCH_PIPELINE_CLI_VERSION


def test_cli_fails_closed_for_invalid_explicit_dataset(tmp_path, capsys):
    path = tmp_path / "bad.json"; path.write_text("{", encoding="utf-8")
    assert main(arguments(path, "fixture")) == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload == {"cli_version": OFFLINE_RESEARCH_PIPELINE_CLI_VERSION, "error_code": "VALIDATION_FAILED", "status": "blocked"}


def test_cli_architecture_boundary_has_no_network_or_trading_dependency():
    source = inspect.getsource(pipeline_cli).lower()
    for forbidden in ("requests", "urllib", "socket", "websocket", "http", "broker", "order", "account", "position", "trade"):
        assert forbidden not in source
