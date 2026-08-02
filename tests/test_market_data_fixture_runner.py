from datetime import UTC, datetime, timedelta
import json

import pytest

from kam_market_ai.market_data.fixture_runner import (
    OFFLINE_RESEARCH_FIXTURE_EXPORT_VERSION,
    build_export_parser,
    build_fixture_export,
    main,
    write_fixture_export,
)


NOW = datetime(2026, 8, 11, 10, tzinfo=UTC)


def row():
    return {"instrument": "MTX", "timeframe": "15m", "opened_at": (NOW - timedelta(minutes=15)).isoformat(), "closed_at": NOW.isoformat(), "open": "100", "high": "102", "low": "99", "close": "101", "volume": "10", "source_record_id": "row-1", "closed": True}


def arguments(input_path, output_path):
    return ["--source", "fixture", "--input", str(input_path), "--output", str(output_path), "--provider-id", "export-fixture", "--dataset-id", "export-dataset", "--instruments", "MTX", "--timeframe", "15m", "--start-at", (NOW - timedelta(hours=1)).isoformat(), "--end-at", (NOW + timedelta(hours=1)).isoformat(), "--as-of", (NOW + timedelta(hours=1)).isoformat(), "--captured-at", NOW.isoformat()]


def test_export_is_deterministic_and_contains_metadata_and_hash(tmp_path):
    source = tmp_path / "fixture.json"; source.write_text(json.dumps([row()]), encoding="utf-8")
    args = build_export_parser().parse_args(arguments(source, (tmp_path / "one.json").resolve()))
    first = build_fixture_export(args)
    second = build_fixture_export(args)
    payload = json.loads(first.serialize())
    assert first.serialize() == second.serialize()
    assert payload["metadata"]["export_version"] == OFFLINE_RESEARCH_FIXTURE_EXPORT_VERSION
    assert payload["export_hash"] == first.export_hash


def test_runner_writes_only_to_explicit_new_absolute_json_path(tmp_path):
    source = tmp_path / "fixture.json"; source.write_text(json.dumps([row()]), encoding="utf-8")
    output = (tmp_path / "result.json").resolve()
    args = build_export_parser().parse_args(arguments(source, output))
    export = write_fixture_export(args, output)
    assert json.loads(output.read_text(encoding="utf-8"))["export_hash"] == export.export_hash
    with pytest.raises(ValueError, match="overwrite"):
        write_fixture_export(args, output)


def test_runner_fail_closed_for_relative_non_json_and_missing_parent_paths(tmp_path):
    source = tmp_path / "fixture.json"; source.write_text(json.dumps([row()]), encoding="utf-8")
    args = build_export_parser().parse_args(arguments(source, (tmp_path / "result.json").resolve()))
    with pytest.raises(ValueError, match="absolute"):
        write_fixture_export(args, __import__("pathlib").Path("relative.json"))
    with pytest.raises(ValueError, match=".json"):
        write_fixture_export(args, (tmp_path / "result.txt").resolve())
    with pytest.raises(ValueError, match="directory"):
        write_fixture_export(args, (tmp_path / "missing" / "result.json").resolve())


def test_main_returns_blocked_json_without_overwriting(tmp_path, capsys):
    source = tmp_path / "fixture.json"; source.write_text(json.dumps([row()]), encoding="utf-8")
    output = (tmp_path / "result.json").resolve(); output.write_text("existing", encoding="utf-8")
    assert main(arguments(source, output)) == 2
    assert json.loads(capsys.readouterr().out) == {"error_code": "VALIDATION_FAILED", "export_version": OFFLINE_RESEARCH_FIXTURE_EXPORT_VERSION, "status": "blocked"}
    assert output.read_text(encoding="utf-8") == "existing"


def test_explicit_replace_policy_is_the_only_overwrite_path(tmp_path):
    source = tmp_path / "fixture.json"; source.write_text(json.dumps([row()]), encoding="utf-8")
    output = (tmp_path / "result.json").resolve(); output.write_text("old", encoding="utf-8")
    args = build_export_parser().parse_args(arguments(source, output) + ["--overwrite", "replace"])
    export = write_fixture_export(args, output, overwrite_policy=args.overwrite)
    assert json.loads(output.read_text(encoding="utf-8"))["export_hash"] == export.export_hash
