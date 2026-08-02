"""Deterministic ordering and validation for ReplayScenario events."""
from __future__ import annotations
from dataclasses import dataclass
from datetime import timedelta
from hashlib import sha256
from typing import Mapping
from .input_contract import REPLAY_INPUT_CONTRACT_VERSION, ReplayEvent, ReplayEventType, ReplayScenario

REPLAY_TIMELINE_VERSION = "1.0"
_PRIORITY = {ReplayEventType.SCENARIO_START: 0, ReplayEventType.MARKET_OPEN: 1, ReplayEventType.TIMEFRAME_UPDATE: 2, ReplayEventType.CANDLE_CLOSE: 3, ReplayEventType.SESSION_BREAK: 4, ReplayEventType.MARKET_CLOSE: 5, ReplayEventType.DATA_GAP: 6, ReplayEventType.SOURCE_CORRECTION: 7, ReplayEventType.SCENARIO_END: 8}

@dataclass(frozen=True, slots=True)
class ReplayTimelineConfig:
    supported_timeline_versions: frozenset[str] = frozenset({REPLAY_TIMELINE_VERSION})
    timeline_version: str = REPLAY_TIMELINE_VERSION
    event_type_priority: Mapping[ReplayEventType, int] = None
    source_priority: Mapping[str, int] = None
    sequence_start: int = 1
    require_monotonic_occurred_at: bool = True
    require_monotonic_evaluated_at: bool = True
    allow_equal_timestamps: bool = True
    calculate_duration: bool = True
    deterministic_hash_algorithm: str = "sha256"
    reject_out_of_range_events: bool = True
    def __post_init__(self):
        if self.timeline_version != REPLAY_TIMELINE_VERSION or self.sequence_start != 1 or self.deterministic_hash_algorithm != "sha256": raise ValueError("Invalid replay timeline configuration")
        if self.event_type_priority is None: object.__setattr__(self, "event_type_priority", _PRIORITY)
        if self.source_priority is None: object.__setattr__(self, "source_priority", {"historical_fixture": 0, "replay_fixture": 1})
    @classmethod
    def provisional(cls): return cls()

@dataclass(frozen=True, slots=True)
class ReplayTimeline:
    timeline_version: str; scenario_id: str; timezone: str; start_at: object; end_at: object; event_count: int; events: tuple[ReplayEvent, ...]; first_sequence: int | None; last_sequence: int | None; duration: timedelta | None; deterministic_hash: str; valid: bool; warnings: tuple[str, ...] = (); error_codes: tuple[str, ...] = ()

def build_replay_timeline(scenario: ReplayScenario, config: ReplayTimelineConfig) -> ReplayTimeline:
    if not isinstance(config, ReplayTimelineConfig): raise TypeError("config must be ReplayTimelineConfig")
    if not isinstance(scenario, ReplayScenario) or not scenario.valid: return ReplayTimeline(REPLAY_TIMELINE_VERSION, getattr(scenario, "scenario_id", ""), "", None, None, 0, (), None, None, None, "", False, (), ("invalid_scenario",))
    events = tuple(sorted(scenario.events, key=lambda event: (event.occurred_at, config.event_type_priority.get(event.event_type, 999), config.source_priority.get(event.source_type, 999), event.sequence, event.event_id)))
    errors = []
    if [event.sequence for event in events] != list(range(1, len(events) + 1)): errors.append("invalid_sequence")
    if any(event.occurred_at < scenario.start_at or event.occurred_at > scenario.end_at for event in events): errors.append("event_out_of_range")
    if any(events[index].evaluated_at < events[index - 1].evaluated_at for index in range(1, len(events))) and config.require_monotonic_evaluated_at: errors.append("non_monotonic_evaluated_at")
    text = "\n".join(f"{event.event_id}|{event.sequence}|{event.occurred_at.isoformat()}|{event.event_type.value}" for event in events)
    digest = sha256(text.encode("utf-8")).hexdigest()
    return ReplayTimeline(REPLAY_TIMELINE_VERSION, scenario.scenario_id, scenario.timezone, scenario.start_at, scenario.end_at, len(events), events, events[0].sequence if events else None, events[-1].sequence if events else None, scenario.end_at - scenario.start_at if config.calculate_duration else None, digest, not errors, (), tuple(errors))
