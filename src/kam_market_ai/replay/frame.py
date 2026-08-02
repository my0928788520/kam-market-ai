"""Immutable Replay Frame contracts, independent from all decision engines."""
from __future__ import annotations
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Mapping
from .input_contract import ReplayCandleState, ReplayEventType, ReplaySessionState, ReplayTimeframe, ReplayUpdateState

REPLAY_FRAME_VERSION = "1.0"

class ReplayFrameState(StrEnum):
    SCENARIO_STARTED="scenario_started"; ACTIVE="active"; UNCHANGED="unchanged"; PARTIAL_UPDATE="partial_update"; DATA_GAP="data_gap"; CORRECTED="corrected"; STALE="stale"; INVALID="invalid"; BLOCKED="blocked"; SCENARIO_COMPLETED="scenario_completed"
class ReplayEvaluationState(StrEnum):
    NOT_REQUESTED="not_requested"; NOT_EVALUATED="not_evaluated"; EVALUATED="evaluated"; UNAVAILABLE="unavailable"; FAILED="failed"

@dataclass(frozen=True, slots=True)
class ReplayFrameTimeframeState:
    timeframe: ReplayTimeframe
    frame_at: object
    update_state: ReplayUpdateState
    candle_state: ReplayCandleState
    market_data_state: str
    source_snapshot_at: object | None
    inherited_from_event_id: str | None
    inherited_from_frame_id: str | None
    input_snapshot: Mapping[str, Any] | None
    valid: bool
    warnings: tuple[str, ...] = ()
    error_codes: tuple[str, ...] = ()

@dataclass(frozen=True, slots=True)
class ReplayFrame:
    frame_version: str
    frame_id: str
    scenario_id: str
    run_id: str
    frame_sequence: int
    source_event_id: str
    source_event_sequence: int
    event_type: ReplayEventType
    occurred_at: object
    evaluated_at: object
    timezone: str
    symbol: str
    market: str
    session_state: ReplaySessionState
    frame_state: ReplayFrameState
    evaluation_state: ReplayEvaluationState
    changed_timeframes: tuple[ReplayTimeframe, ...]
    timeframe_states: Mapping[ReplayTimeframe, ReplayFrameTimeframeState]
    source_lineage: Mapping[str, str]
    previous_frame_id: str | None
    previous_frame_hash: str | None
    frame_hash: str
    valid: bool
    warnings: tuple[str, ...] = ()
    error_codes: tuple[str, ...] = ()
