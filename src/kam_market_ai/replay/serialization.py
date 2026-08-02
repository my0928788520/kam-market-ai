"""Canonical JSON-safe serialization for Replay input contracts."""
from __future__ import annotations
from dataclasses import asdict, dataclass, is_dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from enum import StrEnum
import json
from typing import Any
from .input_contract import ReplayScenario
from .timeline import ReplayTimeline

REPLAY_SERIALIZATION_VERSION = "1.0"

@dataclass(frozen=True, slots=True)
class ReplaySerializationConfig:
    supported_input_versions: frozenset[str] = frozenset({"1.0"})
    supported_timeline_versions: frozenset[str] = frozenset({"1.0"})
    ensure_ascii: bool = False
    indent: int | None = None
    sort_keys: bool = False
    def __post_init__(self):
        if not self.supported_input_versions or not self.supported_timeline_versions: raise ValueError("Invalid replay serialization configuration")
    @classmethod
    def provisional(cls): return cls()

def _value(value: Any) -> Any:
    if isinstance(value, StrEnum): return value.value
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None: raise ValueError("Naive datetime")
        return value.isoformat()
    if isinstance(value, timedelta): return value.total_seconds()
    if isinstance(value, Decimal):
        if not value.is_finite(): raise ValueError("Non-finite Decimal")
        return str(value)
    if is_dataclass(value): return {key: _value(item) for key, item in asdict(value).items()}
    if isinstance(value, dict): return {str(getattr(key, "value", key)): _value(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)): return [_value(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)): return value
    raise TypeError(f"Unsupported replay value: {type(value).__name__}")

def serialize_replay_scenario(scenario: ReplayScenario, config: ReplaySerializationConfig) -> dict[str, Any]:
    if not isinstance(scenario, ReplayScenario) or scenario.replay_input_version not in config.supported_input_versions: raise ValueError("Unsupported replay scenario")
    return {"replay_serialization_version": REPLAY_SERIALIZATION_VERSION, "payload_type": "replay_scenario", **_value(scenario)}

def serialize_replay_timeline(timeline: ReplayTimeline, config: ReplaySerializationConfig) -> dict[str, Any]:
    if not isinstance(timeline, ReplayTimeline) or timeline.timeline_version not in config.supported_timeline_versions: raise ValueError("Unsupported replay timeline")
    return {"replay_serialization_version": REPLAY_SERIALIZATION_VERSION, "payload_type": "replay_timeline", **_value(timeline)}

def replay_payload_to_canonical_json(payload: dict[str, Any], config: ReplaySerializationConfig) -> str:
    return json.dumps(payload, ensure_ascii=config.ensure_ascii, sort_keys=config.sort_keys, separators=(",", ":"), indent=config.indent, allow_nan=False)
