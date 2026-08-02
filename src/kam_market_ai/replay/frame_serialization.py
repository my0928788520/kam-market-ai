"""Canonical JSON serialization for ReplayFrame and ReplayRun."""
from __future__ import annotations
from dataclasses import asdict, dataclass, is_dataclass
from datetime import datetime, timedelta
from enum import StrEnum
import json
from typing import Any
from .frame import REPLAY_FRAME_VERSION, ReplayFrame
from .runner import REPLAY_RUNNER_VERSION, ReplayRun

REPLAY_FRAME_SERIALIZATION_VERSION = "1.0"

@dataclass(frozen=True, slots=True)
class ReplayFrameSerializationConfig:
    supported_frame_versions: frozenset[str] = frozenset({REPLAY_FRAME_VERSION})
    supported_runner_versions: frozenset[str] = frozenset({REPLAY_RUNNER_VERSION})
    ensure_ascii: bool = False
    indent: int | None = None
    def __post_init__(self):
        if not self.supported_frame_versions or not self.supported_runner_versions: raise ValueError("Invalid replay frame serialization configuration")
    @classmethod
    def provisional(cls): return cls()

def _value(value: Any) -> Any:
    if isinstance(value, StrEnum): return value.value
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None: raise ValueError("Naive datetime")
        return value.isoformat()
    if isinstance(value, timedelta): return value.total_seconds()
    if is_dataclass(value): return {key: _value(item) for key, item in asdict(value).items()}
    if isinstance(value, dict): return {str(getattr(key, "value", key)): _value(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)): return [_value(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)): return value
    raise TypeError(f"Unsupported replay frame value: {type(value).__name__}")

def serialize_replay_frame(frame: ReplayFrame, config: ReplayFrameSerializationConfig) -> dict[str, Any]:
    if not isinstance(frame, ReplayFrame) or frame.frame_version not in config.supported_frame_versions: raise ValueError("Unsupported replay frame")
    return {"replay_frame_serialization_version": REPLAY_FRAME_SERIALIZATION_VERSION, "payload_type": "replay_frame", **_value(frame)}

def serialize_replay_run(run: ReplayRun, config: ReplayFrameSerializationConfig) -> dict[str, Any]:
    if not isinstance(run, ReplayRun) or run.runner_version not in config.supported_runner_versions: raise ValueError("Unsupported replay run")
    return {"replay_frame_serialization_version": REPLAY_FRAME_SERIALIZATION_VERSION, "payload_type": "replay_run", **_value(run)}

def replay_frame_payload_to_canonical_json(payload: dict[str, Any], config: ReplayFrameSerializationConfig) -> str:
    return json.dumps(payload, ensure_ascii=config.ensure_ascii, separators=(",", ":"), indent=config.indent, allow_nan=False)
