from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path


SPEC = importlib.util.spec_from_file_location("probe_fubon_position", Path("tools/probe_fubon_position.py"))
assert SPEC and SPEC.loader
probe = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(probe)


class FakeProcess:
    def __init__(self, *, stdout: str = "", timeout: bool = False) -> None:
        self.stdout = stdout
        self.timeout = timeout
        self.returncode: int | None = 0
        self.terminated = False

    def communicate(self, timeout=None):
        if self.timeout:
            raise subprocess.TimeoutExpired("probe", timeout)
        return self.stdout, ""

    def terminate(self) -> None:
        self.terminated = True
        self.returncode = -15

    def wait(self, timeout=None) -> int:
        assert self.terminated
        return self.returncode or -15

    def kill(self) -> None:
        self.terminated = True
        self.returncode = -9

    def poll(self):
        return self.returncode


def output(tmp_path):
    return tmp_path / "debug" / "position" / "probe_result.json"


def test_dry_run_writes_no_child_result(tmp_path) -> None:
    result = probe.run_probe(method="hybrid", timeout=30, output=output(tmp_path), dry_run=True)
    assert result["mode"] == "dry-run"
    assert result["child_started"] is False
    assert json.loads(output(tmp_path).read_text(encoding="utf-8"))["mode"] == "dry-run"


def test_cli_defaults_to_dry_run() -> None:
    assert probe.parse_args([]).dry_run is True
    assert probe.parse_args(["--live"]).dry_run is False


def test_cli_live_failure_returns_nonzero(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        probe,
        "run_probe",
        lambda **kwargs: {"mode": "live", "status": "exception"},
    )
    assert probe.main(["--live", "--output", str(output(tmp_path))]) == 1


def test_cli_live_success_returns_zero(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        probe,
        "run_probe",
        lambda **kwargs: {"mode": "live", "status": "completed"},
    )
    assert probe.main(["--live", "--output", str(output(tmp_path))]) == 0


def test_windows_account_probe_launcher_is_read_only() -> None:
    source = Path("tools/start_fubon_read_only_account_probe.ps1").read_text(encoding="utf-8")
    assert "probe_fubon_position.py" in source
    assert "--live" in source
    assert "不會送出、修改或取消任何委託" in source
    for forbidden in ("place_order", "cancel_order", "modify_order"):
        assert forbidden not in source


def test_normal_return_records_only_wrapper_summary(tmp_path) -> None:
    child = {"status": "completed", "summary": {"result_type": "builtins.CustomReturnType", "data_type": "builtins.list", "data_row_count": 1}}
    result = probe.run_probe(method="hybrid", timeout=30, output=output(tmp_path), dry_run=False,
                             popen_factory=lambda *args, **kwargs: FakeProcess(stdout=json.dumps(child)))
    assert result["status"] == "completed"
    assert result["summary"]["data_row_count"] == 1
    assert result["child_exited"] is True


def test_child_uses_repository_root_and_src_from_any_cwd(tmp_path, monkeypatch) -> None:
    captured = {}
    monkeypatch.chdir(tmp_path)
    child = {"status": "completed", "summary": {"data_row_count": 0}}

    def factory(*args, **kwargs):
        captured.update(kwargs)
        return FakeProcess(stdout=json.dumps(child))

    probe.run_probe(method="hybrid", timeout=30, output=output(tmp_path), dry_run=False, popen_factory=factory)
    assert captured["cwd"] == str(probe.REPOSITORY_ROOT)
    assert captured["env"]["PYTHONPATH"].split(os.pathsep)[:2] == [str(probe.REPOSITORY_ROOT), str(probe.REPOSITORY_ROOT / "src")]


def test_child_environment_can_import_src_layout() -> None:
    completed = subprocess.run(
        [sys.executable, "-c", "import kam_market_ai; print(kam_market_ai.__name__)"],
        cwd=probe.REPOSITORY_ROOT,
        env=probe.child_environment({}),
        check=True,
        capture_output=True,
        text=True,
    )
    assert completed.stdout.strip() == "kam_market_ai"


def test_timeout_terminates_and_has_no_child_left(tmp_path) -> None:
    process = FakeProcess(timeout=True)
    result = probe.run_probe(method="single", timeout=1, output=output(tmp_path), dry_run=False,
                             popen_factory=lambda *args, **kwargs: process)
    assert process.terminated is True
    assert result["status"] == "timeout"
    assert result["child_exited"] is True
    assert result["retried"] is False


def test_worker_exception_is_recorded_without_message(tmp_path) -> None:
    child = {"status": "exception", "exception_type": "RuntimeError", "message": "secret"}
    result = probe.run_probe(method="hybrid", timeout=30, output=output(tmp_path), dry_run=False,
                             popen_factory=lambda *args, **kwargs: FakeProcess(stdout=json.dumps(child)))
    assert result["status"] == "exception"
    assert result["exception_type"] == "RuntimeError"
    assert "message" not in result


def test_missing_module_name_is_reported_without_details(tmp_path) -> None:
    child = {"status": "exception", "exception_type": "ModuleNotFoundError", "missing_module": "kam_market_ai"}
    result = probe.run_probe(method="hybrid", timeout=30, output=output(tmp_path), dry_run=False,
                             popen_factory=lambda *args, **kwargs: FakeProcess(stdout=json.dumps(child)))
    assert result["missing_module"] == "kam_market_ai"


def test_sensitive_values_are_redacted() -> None:
    safe = probe.redact_mapping({"account": "123", "name": "person", "token": "secret", "symbol": "MTX"})
    assert safe == {"account": "<redacted>", "name": "<redacted>", "token": "<redacted>", "symbol": "MTX"}


def test_result_summary_does_not_capture_data_rows() -> None:
    class FakeResult:
        is_success = True
        data = [{"account": "123", "symbol": "MTX"}]

    summary = probe.result_summary(FakeResult())
    assert summary["data_row_count"] == 1
    assert "data" not in summary
