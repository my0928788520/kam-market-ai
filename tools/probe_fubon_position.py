"""Bounded, read-only diagnostic for Fubon futures position query wrappers.

Default mode is dry-run. A live query can only run in this file's worker
subprocess; the parent process never imports the Fubon SDK.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any, Protocol


SENSITIVE_KEY_PARTS = ("account", "name", "personal", "identity", "token", "password", "secret", "cert", "branch")
METHODS = ("hybrid", "single")
REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


class ProcessLike(Protocol):
    returncode: int | None

    def communicate(self, timeout: float | None = None) -> tuple[str, str]: ...
    def terminate(self) -> None: ...
    def kill(self) -> None: ...
    def wait(self, timeout: float | None = None) -> int: ...
    def poll(self) -> int | None: ...


def utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def event(events: list[dict[str, str]], phase: str) -> None:
    events.append({"phase": phase, "at": utc_now()})


def safe_public_fields(value: object) -> list[str]:
    """Return names only; never return values from an SDK wrapper."""
    return sorted(name for name in dir(value) if not name.startswith("_"))


def redact_mapping(value: Any, key: str = "") -> Any:
    """Used only for safe local metadata; all sensitive keys lose their value."""
    if any(part in key.lower() for part in SENSITIVE_KEY_PARTS):
        return "<redacted>"
    if isinstance(value, Mapping):
        return {str(item_key): redact_mapping(item_value, str(item_key)) for item_key, item_value in value.items()}
    if isinstance(value, list):
        return [redact_mapping(item, key) for item in value]
    if isinstance(value, tuple):
        return [redact_mapping(item, key) for item in value]
    return value


def result_summary(result: object) -> dict[str, object]:
    """Summarize only the return wrapper structure, never its position rows."""
    data = getattr(result, "data", None)
    if isinstance(data, Mapping):
        data_type, row_count = "mapping", len(data)
    elif isinstance(data, Sequence) and not isinstance(data, (str, bytes, bytearray)):
        data_type, row_count = f"{type(data).__module__}.{type(data).__qualname__}", len(data)
    elif data is None:
        data_type, row_count = None, None
    else:
        data_type, row_count = f"{type(data).__module__}.{type(data).__qualname__}", None
    return {
        "result_type": f"{type(result).__module__}.{type(result).__qualname__}",
        "public_fields": safe_public_fields(result),
        "has_data": hasattr(result, "data"),
        "data_type": data_type,
        "data_row_count": row_count,
        "is_success": getattr(result, "is_success", None),
        "success": getattr(result, "success", None),
        "message_present": getattr(result, "message", None) is not None,
        "error_present": getattr(result, "error", None) is not None,
        "code_present": getattr(result, "code", None) is not None,
        "status_present": getattr(result, "status", None) is not None,
    }


def read_events(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        return []
    events: list[dict[str, str]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(item, dict) and isinstance(item.get("phase"), str) and isinstance(item.get("at"), str):
            events.append({"phase": item["phase"], "at": item["at"]})
    return events


def append_progress(path: Path, phase: str) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({"phase": phase, "at": utc_now()}) + "\n")
        handle.flush()


def write_output(path: Path, payload: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(redact_mapping(dict(payload)), ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def child_environment(base: Mapping[str, str] | None = None) -> dict[str, str]:
    """Build an isolated import path for the repository's src layout."""
    environment = dict(os.environ if base is None else base)
    paths = [str(REPOSITORY_ROOT), str(REPOSITORY_ROOT / "src")]
    existing = environment.get("PYTHONPATH")
    if existing:
        paths.append(existing)
    environment["PYTHONPATH"] = os.pathsep.join(paths)
    return environment


def exception_payload(error: Exception) -> dict[str, str]:
    payload = {"status": "exception", "exception_type": type(error).__name__}
    if isinstance(error, ModuleNotFoundError) and error.name:
        payload["missing_module"] = error.name
    return payload


def worker(method: str, progress: Path) -> int:
    """The only place where a live SDK query can execute."""
    try:
        append_progress(progress, "process_start")
        from fubon_neo.sdk import FubonSDK
        from kam_market_ai.authorization.bootstrap import AuthorizationSettings, CertificatePasswordMode

        append_progress(progress, "sdk_imported")
        settings = AuthorizationSettings.from_local_env()
        if settings.missing_fields:
            raise RuntimeError("LOCAL_AUTH_CONFIGURATION_INCOMPLETE")
        sdk = FubonSDK()
        append_progress(progress, "sdk_created")
        credentials = settings.credentials
        append_progress(progress, "login_started")
        login = sdk.login(credentials.personal_id, credentials.password, credentials.certificate_path) if settings.certificate_password_mode is CertificatePasswordMode.DEFAULT else sdk.login(credentials.personal_id, credentials.password, credentials.certificate_path, credentials.certificate_password)
        if getattr(login, "is_success", False) is not True:
            raise RuntimeError("LOGIN_REJECTED")
        append_progress(progress, "login_completed")
        accounts = tuple(getattr(login, "data", ()) or ())
        append_progress(progress, "accounts_loaded")
        futopt = tuple(account for account in accounts if getattr(account, "account_type", None) == "futopt")
        if len(futopt) != 1:
            raise RuntimeError("FUTOPT_ACCOUNT_AMBIGUOUS_OR_MISSING")
        append_progress(progress, "futopt_account_selected")
        query: Callable[[object], object] = sdk.futopt_accounting.query_hybrid_position if method == "hybrid" else sdk.futopt_accounting.query_single_position
        append_progress(progress, "query_started")
        result = query(futopt[0])
        append_progress(progress, "query_completed")
        print(json.dumps({"status": "completed", "summary": result_summary(result)}, ensure_ascii=False))
        return 0
    except Exception as error:
        append_progress(progress, "exception")
        print(json.dumps(exception_payload(error), ensure_ascii=False))
        return 1


def run_probe(
    *,
    method: str,
    timeout: float,
    output: Path,
    dry_run: bool,
    popen_factory: Callable[..., ProcessLike] = subprocess.Popen,
) -> dict[str, object]:
    if method not in METHODS:
        raise ValueError("unsupported method")
    if timeout <= 0:
        raise ValueError("timeout must be positive")
    events: list[dict[str, str]] = []
    event(events, "process_start")
    if dry_run:
        event(events, "dry_run")
        payload: dict[str, object] = {"mode": "dry-run", "method": method, "events": events, "child_started": False}
        write_output(output, payload)
        return payload

    progress_fd, progress_name = tempfile.mkstemp(prefix="kam-fubon-position-", suffix=".jsonl")
    os.close(progress_fd)
    progress = Path(progress_name)
    process: ProcessLike | None = None
    try:
        command = [sys.executable, str(Path(__file__).resolve()), "--_worker", "--method", method, "--progress", str(progress)]
        process = popen_factory(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=str(REPOSITORY_ROOT),
            env=child_environment(),
        )
        try:
            stdout, _stderr = process.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            event(events, "timeout")
            process.terminate()
            try:
                exit_code = process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                exit_code = process.wait(timeout=10)
            payload = {
                "mode": "live", "method": method, "status": "timeout", "events": events + read_events(progress),
                "exit_code": exit_code, "child_exited": process.poll() is not None, "retried": False,
            }
            write_output(output, payload)
            return payload
        child = json.loads(stdout) if stdout.strip() else {"status": "exception", "exception_type": "EMPTY_WORKER_OUTPUT"}
        payload = {
            "mode": "live", "method": method, "status": child.get("status", "exception"),
            "events": events + read_events(progress), "exit_code": process.returncode,
            "child_exited": process.poll() is not None, "retried": False,
        }
        if child.get("status") == "completed":
            payload["summary"] = child.get("summary")
        else:
            payload["exception_type"] = child.get("exception_type", "UNKNOWN")
            if child.get("missing_module"):
                payload["missing_module"] = child["missing_module"]
        write_output(output, payload)
        return payload
    finally:
        try:
            progress.unlink(missing_ok=True)
        except OSError:
            pass


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Bounded read-only Fubon futures position probe")
    parser.add_argument("--method", choices=METHODS, default="hybrid")
    parser.add_argument("--timeout", type=float, default=30)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", dest="dry_run", action="store_true", help="Never import or query the SDK")
    mode.add_argument("--live", dest="dry_run", action="store_false", help="Run the bounded read-only worker subprocess")
    parser.set_defaults(dry_run=True)
    parser.add_argument("--output", default="debug/position/probe_result.json")
    parser.add_argument("--_worker", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--progress", type=Path, help=argparse.SUPPRESS)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    if args._worker:
        if args.progress is None:
            raise SystemExit("worker requires progress path")
        return worker(args.method, args.progress)
    payload = run_probe(method=args.method, timeout=args.timeout, output=Path(args.output), dry_run=args.dry_run)
    print(json.dumps({"status": payload.get("status", payload.get("mode")), "output": str(args.output)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
