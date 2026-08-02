from datetime import UTC, datetime, timedelta
import inspect
import json

from kam_market_ai.market_data import fixture_runner, pipeline_cli
from kam_market_ai.market_data.pipeline_cli import main


NOW = datetime(2026, 8, 12, 10, tzinfo=UTC)


def row():
    return {"instrument": "MTX", "timeframe": "15m", "opened_at": (NOW - timedelta(minutes=15)).isoformat(), "closed_at": NOW.isoformat(), "open": "100", "high": "102", "low": "99", "close": "101", "volume": "10", "source_record_id": "e2e-1", "closed": True}


def arguments(input_path, output_path, overwrite="forbid"):
    return ["--source", "fixture", "--input", str(input_path), "--output", str(output_path), "--overwrite", overwrite, "--provider-id", "e2e-fixture", "--dataset-id", "e2e-dataset", "--instruments", "MTX", "--timeframe", "15m", "--start-at", (NOW - timedelta(hours=1)).isoformat(), "--end-at", (NOW + timedelta(hours=1)).isoformat(), "--as-of", (NOW + timedelta(hours=1)).isoformat(), "--captured-at", NOW.isoformat()]


def test_cli_to_explicit_export_end_to_end_is_deterministic(tmp_path, capsys):
    input_path = tmp_path / "fixture.json"; input_path.write_text(json.dumps([row()]), encoding="utf-8")
    first_path = (tmp_path / "first.json").resolve()
    second_path = (tmp_path / "second.json").resolve()
    assert main(arguments(input_path, first_path)) == 0
    first_stdout = capsys.readouterr().out
    assert main(arguments(input_path, second_path)) == 0
    second_stdout = capsys.readouterr().out
    assert first_stdout == second_stdout
    assert first_path.read_text(encoding="utf-8") == second_path.read_text(encoding="utf-8")
    payload = json.loads(first_stdout)
    assert payload["metadata"]["source"] == "fixture"
    assert payload["pipeline"]["pipeline"]["scan_status"] == "completed"


def test_existing_output_is_fail_closed_with_stable_error(tmp_path, capsys):
    input_path = tmp_path / "fixture.json"; input_path.write_text(json.dumps([row()]), encoding="utf-8")
    output_path = (tmp_path / "result.json").resolve(); output_path.write_text("existing", encoding="utf-8")
    assert main(arguments(input_path, output_path)) == 2
    assert json.loads(capsys.readouterr().out)["error_code"] == "VALIDATION_FAILED"
    assert output_path.read_text(encoding="utf-8") == "existing"


def test_v1_1_cli_and_runner_have_no_network_or_trading_boundary():
    source = inspect.getsource(pipeline_cli).lower() + inspect.getsource(fixture_runner).lower()
    for forbidden in ("requests", "urllib", "socket", "websocket", "http", "broker", "order", "account", "position", "trade"):
        assert forbidden not in source
