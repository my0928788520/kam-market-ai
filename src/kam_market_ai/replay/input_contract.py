"""Frozen, read-only inputs for a future deterministic Replay Runner."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from hashlib import sha256
from typing import Any, Mapping
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

REPLAY_INPUT_CONTRACT_VERSION = "1.0"


class ReplayTimeframe(StrEnum):
    M15 = "15m"; M60 = "60m"; D1 = "1d"; W1 = "1w"


class ReplayEventType(StrEnum):
    SCENARIO_START = "scenario_start"; MARKET_OPEN = "market_open"; TIMEFRAME_UPDATE = "timeframe_update"; CANDLE_CLOSE = "candle_close"; SESSION_BREAK = "session_break"; MARKET_CLOSE = "market_close"; DATA_GAP = "data_gap"; SOURCE_CORRECTION = "source_correction"; SCENARIO_END = "scenario_end"


class ReplaySessionState(StrEnum):
    PRE_OPEN = "pre_open"; OPEN = "open"; BREAK = "break"; CLOSED = "closed"; HOLIDAY = "holiday"; UNKNOWN = "unknown"


class ReplayUpdateState(StrEnum):
    UPDATED = "updated"; UNCHANGED = "unchanged"; UNAVAILABLE = "unavailable"; STALE = "stale"; INVALID = "invalid"


class ReplayCandleState(StrEnum):
    FORMING = "forming"; CLOSED = "closed"; UNAVAILABLE = "unavailable"


_TIMEFRAMES = (ReplayTimeframe.M15, ReplayTimeframe.M60, ReplayTimeframe.D1, ReplayTimeframe.W1)


@dataclass(frozen=True, slots=True)
class ReplayInputConfig:
    supported_input_versions: frozenset[str] = frozenset({REPLAY_INPUT_CONTRACT_VERSION})
    required_timeframes: tuple[ReplayTimeframe, ...] = _TIMEFRAMES
    timezone_policy: str = "exact_zoneinfo"
    reject_naive_datetime: bool = True
    reject_duplicate_event_id: bool = True
    reject_duplicate_sequence: bool = True
    require_scenario_start: bool = True
    require_scenario_end: bool = True
    require_contiguous_sequence: bool = True
    allow_data_gap: bool = True
    allow_source_correction: bool = True
    maximum_event_count: int = 4096
    maximum_warning_count: int = 64
    deterministic_id_algorithm: str = "sha256"
    source_type_whitelist: frozenset[str] = frozenset({"historical_fixture", "replay_fixture"})
    source_version_policy: str = "required"

    def __post_init__(self) -> None:
        if (not self.supported_input_versions or self.required_timeframes != _TIMEFRAMES or self.timezone_policy != "exact_zoneinfo" or self.maximum_event_count <= 0 or self.maximum_warning_count <= 0 or self.deterministic_id_algorithm != "sha256" or not self.source_type_whitelist or self.source_version_policy != "required"):
            raise ValueError("Invalid replay input configuration")

    @classmethod
    def provisional(cls) -> "ReplayInputConfig": return cls()


@dataclass(frozen=True, slots=True)
class ReplayTimeframeSnapshot:
    timeframe: ReplayTimeframe
    snapshot_at: datetime
    update_state: ReplayUpdateState
    candle_state: ReplayCandleState
    market_data_state: str
    position_input: Mapping[str, Any] | None
    trend_input: Mapping[str, Any] | None
    structure_input: Mapping[str, Any] | None
    timing_input: Mapping[str, Any] | None
    source_version: str
    data_quality: str
    valid: bool
    warnings: tuple[str, ...] = ()
    error_codes: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ReplayEvent:
    event_id: str
    sequence: int
    event_type: ReplayEventType
    occurred_at: datetime
    evaluated_at: datetime
    timezone: str
    symbol: str
    market: str
    session_state: ReplaySessionState
    changed_timeframes: tuple[ReplayTimeframe, ...]
    timeframe_snapshots: Mapping[ReplayTimeframe, ReplayTimeframeSnapshot]
    source_type: str
    source_version: str
    source_lineage: Mapping[str, str]
    data_quality: str
    valid: bool
    warnings: tuple[str, ...] = ()
    error_codes: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ReplayScenario:
    replay_input_version: str
    scenario_id: str
    name: str
    title: str
    description: str
    symbol: str
    market: str
    session: ReplaySessionState
    timezone: str
    timeframe_set: tuple[ReplayTimeframe, ...]
    start_at: datetime | None
    end_at: datetime | None
    created_for: str
    source_type: str
    source_version: str
    source_lineage: Mapping[str, str]
    tags: tuple[str, ...]
    events: tuple[ReplayEvent, ...]
    expected_event_count: int
    valid: bool
    warnings: tuple[str, ...] = ()
    error_codes: tuple[str, ...] = ()


def deterministic_scenario_id(*, name: str, symbol: str, market: str, timezone: str, start_at: datetime, end_at: datetime, source_version: str) -> str:
    canonical = "|".join((name, symbol, market, timezone, start_at.isoformat(), end_at.isoformat(), source_version))
    return sha256(canonical.encode("utf-8")).hexdigest()


def deterministic_event_id(scenario_id: str, sequence: int, occurred_at: datetime, event_type: ReplayEventType) -> str:
    return sha256(f"{scenario_id}|{sequence}|{occurred_at.isoformat()}|{event_type.value}".encode("utf-8")).hexdigest()


def _zone_ok(value: datetime | None, timezone: str) -> bool:
    if value is None or value.tzinfo is None or value.utcoffset() is None:
        return False
    try: zone = ZoneInfo(timezone)
    except ZoneInfoNotFoundError: return False
    return getattr(value.tzinfo, "key", None) == zone.key


def _invalid(metadata: Mapping[str, Any], errors: tuple[str, ...]) -> ReplayScenario:
    return ReplayScenario(REPLAY_INPUT_CONTRACT_VERSION, "", str(metadata.get("name", "invalid")), "Replay input unavailable", "", str(metadata.get("symbol", "")), str(metadata.get("market", "")), ReplaySessionState.UNKNOWN, str(metadata.get("timezone", "")), _TIMEFRAMES, None, None, "replay", str(metadata.get("source_type", "")), str(metadata.get("source_version", "")), {}, (), (), 0, False, (), errors)


def build_replay_scenario(metadata: Mapping[str, Any], events: tuple[ReplayEvent, ...], config: ReplayInputConfig) -> ReplayScenario:
    """Validate static historical input; never evaluates an engine or clock."""
    if not isinstance(config, ReplayInputConfig): raise TypeError("config must be ReplayInputConfig")
    if not isinstance(metadata, Mapping) or not isinstance(events, tuple): return _invalid({}, ("input_type_mismatch",))
    try:
        timezone = str(metadata["timezone"]); start_at = metadata["start_at"]; end_at = metadata["end_at"]
        version = str(metadata["source_version"]); source_type = str(metadata["source_type"])
        if str(metadata.get("replay_input_version", REPLAY_INPUT_CONTRACT_VERSION)) not in config.supported_input_versions: return _invalid(metadata, ("unsupported_input_version",))
        if source_type not in config.source_type_whitelist or not version: return _invalid(metadata, ("unsupported_source",))
        if not _zone_ok(start_at, timezone) or not _zone_ok(end_at, timezone): return _invalid(metadata, ("timezone_mismatch",))
        if start_at > end_at or len(events) > config.maximum_event_count: return _invalid(metadata, ("invalid_range",))
        ids, sequences = [event.event_id for event in events], [event.sequence for event in events]
        if len(set(ids)) != len(ids) or len(set(sequences)) != len(sequences): return _invalid(metadata, ("duplicate_event",))
        if config.require_contiguous_sequence and sequences != list(range(1, len(events) + 1)): return _invalid(metadata, ("invalid_sequence",))
        if config.require_scenario_start and (not events or events[0].event_type is not ReplayEventType.SCENARIO_START): return _invalid(metadata, ("missing_scenario_start",))
        if config.require_scenario_end and (not events or events[-1].event_type is not ReplayEventType.SCENARIO_END): return _invalid(metadata, ("missing_scenario_end",))
        for event in events:
            if not _zone_ok(event.occurred_at, timezone) or not _zone_ok(event.evaluated_at, timezone) or event.evaluated_at < event.occurred_at or not start_at <= event.occurred_at <= end_at: return _invalid(metadata, ("invalid_event_timestamp",))
            if event.event_type is ReplayEventType.DATA_GAP and not config.allow_data_gap: return _invalid(metadata, ("data_gap_disabled",))
            if event.event_type is ReplayEventType.SOURCE_CORRECTION and not config.allow_source_correction: return _invalid(metadata, ("source_correction_disabled",))
        scenario_id = deterministic_scenario_id(name=str(metadata["name"]), symbol=str(metadata["symbol"]), market=str(metadata["market"]), timezone=timezone, start_at=start_at, end_at=end_at, source_version=version)
        return ReplayScenario(REPLAY_INPUT_CONTRACT_VERSION, scenario_id, str(metadata["name"]), str(metadata.get("title", metadata["name"])), str(metadata.get("description", "")), str(metadata["symbol"]), str(metadata["market"]), ReplaySessionState(str(metadata.get("session", "unknown"))), timezone, _TIMEFRAMES, start_at, end_at, str(metadata.get("created_for", "replay")), source_type, version, dict(metadata.get("source_lineage", {})), tuple(metadata.get("tags", ())), events, int(metadata.get("expected_event_count", len(events))), True)
    except (KeyError, TypeError, ValueError): return _invalid(metadata, ("invalid_scenario",))
