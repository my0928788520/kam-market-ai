"""Deterministic input-only replay frame generation; no runner UI or engines."""
from __future__ import annotations
from dataclasses import asdict, dataclass
from hashlib import sha256
import json
from typing import Callable, Iterator, Mapping, Protocol
from .frame import REPLAY_FRAME_VERSION, ReplayEvaluationState, ReplayFrame, ReplayFrameState, ReplayFrameTimeframeState
from .input_contract import REPLAY_INPUT_CONTRACT_VERSION, ReplayCandleState, ReplayEvent, ReplayEventType, ReplayTimeframe, ReplayUpdateState
from .timeline import REPLAY_TIMELINE_VERSION, ReplayTimeline

REPLAY_RUNNER_VERSION = "1.0"
_TIMEFRAMES=(ReplayTimeframe.M15, ReplayTimeframe.M60, ReplayTimeframe.D1, ReplayTimeframe.W1)

class ReplayEvaluator(Protocol):
    def __call__(self, frame: ReplayFrame) -> object: ...

@dataclass(frozen=True, slots=True)
class ReplayRunnerConfig:
    runner_version: str = REPLAY_RUNNER_VERSION
    supported_timeline_versions: frozenset[str] = frozenset({REPLAY_TIMELINE_VERSION})
    supported_input_versions: frozenset[str] = frozenset({REPLAY_INPUT_CONTRACT_VERSION})
    supported_frame_versions: frozenset[str] = frozenset({REPLAY_FRAME_VERSION})
    sequence_start: int = 1
    stop_on_invalid_event: bool = True
    stop_on_data_gap: bool = True
    stop_on_source_correction_error: bool = True
    emit_scenario_boundary_frames: bool = True
    emit_unchanged_frames: bool = True
    maximum_frame_count: int = 4096
    maximum_warning_count: int = 64
    deterministic_hash_algorithm: str = "sha256"
    preserve_event_lineage: bool = True
    preserve_source_lineage: bool = True
    allow_partial_timeframe_update: bool = True
    required_timeframes: tuple[ReplayTimeframe, ...] = _TIMEFRAMES
    evaluator_mode: str = "input_only"
    fail_closed_policy: str = "block"
    def __post_init__(self):
        if (self.runner_version != REPLAY_RUNNER_VERSION or not self.supported_timeline_versions or not self.supported_input_versions or not self.supported_frame_versions or self.sequence_start != 1 or self.maximum_frame_count <= 0 or self.maximum_warning_count <= 0 or self.deterministic_hash_algorithm != "sha256" or self.required_timeframes != _TIMEFRAMES or self.evaluator_mode not in {"input_only", "injected_evaluator"} or self.fail_closed_policy != "block"):
            raise ValueError("Invalid replay runner configuration")
    @classmethod
    def provisional(cls): return cls()

@dataclass(frozen=True, slots=True)
class ReplayRun:
    runner_version: str; frame_version: str; scenario_id: str; timeline_version: str; timeline_hash: str; run_id: str; started_at: object; ended_at: object; timezone: str; source_event_count: int; emitted_frame_count: int; first_frame_sequence: int | None; last_frame_sequence: int | None; frames: tuple[ReplayFrame, ...]; run_hash: str; valid: bool; completion_state: str; warnings: tuple[str, ...] = (); error_codes: tuple[str, ...] = (); stopped_at_event_id: str | None = None; stopped_at_sequence: int | None = None; source_lineage: Mapping[str, str] = None

def _config_hash(config: ReplayRunnerConfig) -> str:
    value = {key: str(item) for key, item in asdict(config).items()}
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()

def _run_id(timeline: ReplayTimeline, config: ReplayRunnerConfig) -> str:
    return sha256(f"{timeline.scenario_id}|{timeline.deterministic_hash}|{config.runner_version}|{REPLAY_FRAME_VERSION}|{_config_hash(config)}".encode("utf-8")).hexdigest()

def _snapshot_payload(snapshot: object | None) -> Mapping[str, object] | None:
    if snapshot is None: return None
    return {"position_input": snapshot.position_input, "trend_input": snapshot.trend_input, "structure_input": snapshot.structure_input, "timing_input": snapshot.timing_input, "source_version": snapshot.source_version, "data_quality": snapshot.data_quality}

def _unavailable(timeframe: ReplayTimeframe, at: object, *, state: ReplayUpdateState=ReplayUpdateState.UNAVAILABLE, code: str="unavailable") -> ReplayFrameTimeframeState:
    return ReplayFrameTimeframeState(timeframe, at, state, ReplayCandleState.UNAVAILABLE, "unavailable", None, None, None, None, False, (), (code,))

def _frame_hash(run_id: str, event: ReplayEvent, sequence: int, prior: str | None, state: ReplayFrameState, slots: Mapping[ReplayTimeframe, ReplayFrameTimeframeState]) -> str:
    text = "|".join((run_id, event.event_id, str(sequence), prior or "", state.value, *(f"{timeframe.value}:{slot.update_state.value}:{slot.source_snapshot_at}" for timeframe, slot in slots.items())))
    return sha256(text.encode("utf-8")).hexdigest()

def _frame_state(event: ReplayEvent, changed: tuple[ReplayTimeframe, ...]) -> ReplayFrameState:
    if not event.valid: return ReplayFrameState.INVALID
    if event.event_type is ReplayEventType.SCENARIO_START: return ReplayFrameState.SCENARIO_STARTED
    if event.event_type is ReplayEventType.SCENARIO_END: return ReplayFrameState.SCENARIO_COMPLETED
    if event.event_type is ReplayEventType.DATA_GAP: return ReplayFrameState.DATA_GAP
    if event.event_type is ReplayEventType.SOURCE_CORRECTION: return ReplayFrameState.CORRECTED
    if any(snapshot.update_state is ReplayUpdateState.STALE for snapshot in event.timeframe_snapshots.values()): return ReplayFrameState.STALE
    if not changed: return ReplayFrameState.UNCHANGED
    if len(changed) != len(_TIMEFRAMES): return ReplayFrameState.PARTIAL_UPDATE
    return ReplayFrameState.ACTIVE

def iter_replay_frames(timeline: ReplayTimeline, config: ReplayRunnerConfig, evaluator: ReplayEvaluator | None = None) -> Iterator[ReplayFrame]:
    """Yield deterministic input-only frames. Injected evaluator is intentionally not executed in Phase 2."""
    if not isinstance(config, ReplayRunnerConfig): raise TypeError("config must be ReplayRunnerConfig")
    if evaluator is not None or config.evaluator_mode != "input_only": raise ValueError("Phase 2 supports input_only evaluation")
    if not isinstance(timeline, ReplayTimeline) or not timeline.valid or timeline.timeline_version not in config.supported_timeline_versions: return
    inherited: dict[ReplayTimeframe, ReplayFrameTimeframeState] = {}
    prior_id = prior_hash = None; run_id = _run_id(timeline, config); emitted = 0
    for event in timeline.events:
        if emitted >= config.maximum_frame_count: return
        if event.event_type in {ReplayEventType.SCENARIO_START, ReplayEventType.SCENARIO_END} and not config.emit_scenario_boundary_frames: continue
        changed = tuple(event.changed_timeframes)
        if not changed and event.timeframe_snapshots: changed = tuple(event.timeframe_snapshots)
        state = _frame_state(event, changed)
        if state is ReplayFrameState.UNCHANGED and not config.emit_unchanged_frames: continue
        slots: dict[ReplayTimeframe, ReplayFrameTimeframeState] = {}
        for timeframe in _TIMEFRAMES:
            snapshot = event.timeframe_snapshots.get(timeframe)
            affected_gap = event.event_type is ReplayEventType.DATA_GAP and (not changed or timeframe in changed)
            if snapshot is not None:
                slot = ReplayFrameTimeframeState(timeframe, event.occurred_at, snapshot.update_state, snapshot.candle_state, snapshot.market_data_state, snapshot.snapshot_at, None, None, _snapshot_payload(snapshot), snapshot.valid, snapshot.warnings[:config.maximum_warning_count], snapshot.error_codes)
            elif affected_gap:
                slot = _unavailable(timeframe, event.occurred_at, code="data_gap")
            elif timeframe in inherited:
                previous = inherited[timeframe]
                slot = ReplayFrameTimeframeState(timeframe, event.occurred_at, ReplayUpdateState.UNCHANGED, previous.candle_state, previous.market_data_state, previous.source_snapshot_at, previous.inherited_from_event_id or event.event_id, prior_id, previous.input_snapshot, previous.valid, previous.warnings, previous.error_codes)
            else: slot = _unavailable(timeframe, event.occurred_at)
            slots[timeframe] = slot
        frame_sequence = emitted + 1; digest = _frame_hash(run_id, event, frame_sequence, prior_hash, state, slots); frame = ReplayFrame(REPLAY_FRAME_VERSION, sha256(f"{run_id}|{frame_sequence}|{event.event_id}".encode("utf-8")).hexdigest(), timeline.scenario_id, run_id, frame_sequence, event.event_id, event.sequence, event.event_type, event.occurred_at, event.evaluated_at, event.timezone, event.symbol, event.market, event.session_state, state, ReplayEvaluationState.NOT_EVALUATED, changed, slots, dict(event.source_lineage) if config.preserve_source_lineage else {}, prior_id, prior_hash, digest, event.valid, event.warnings[:config.maximum_warning_count], event.error_codes)
        yield frame; emitted += 1; prior_id, prior_hash = frame.frame_id, frame.frame_hash; inherited = slots
        if not event.valid and config.stop_on_invalid_event: return
        if event.event_type is ReplayEventType.DATA_GAP and config.stop_on_data_gap: return

def run_replay_timeline(timeline: ReplayTimeline, config: ReplayRunnerConfig, evaluator: ReplayEvaluator | None = None) -> ReplayRun:
    if not isinstance(config, ReplayRunnerConfig): raise TypeError("config must be ReplayRunnerConfig")
    if not isinstance(timeline, ReplayTimeline) or not timeline.valid or timeline.timeline_version not in config.supported_timeline_versions:
        return ReplayRun(REPLAY_RUNNER_VERSION, REPLAY_FRAME_VERSION, getattr(timeline, "scenario_id", ""), getattr(timeline, "timeline_version", ""), getattr(timeline, "deterministic_hash", ""), "", None, None, "", 0, 0, None, None, (), "", False, "blocked", (), ("invalid_timeline",), None, None, {})
    try:
        frames = tuple(iter_replay_frames(timeline, config, evaluator)); stopped = frames[-1] if frames and len(frames) < len(timeline.events) else None
        blocked = bool(stopped and stopped.frame_state in {ReplayFrameState.DATA_GAP, ReplayFrameState.INVALID})
        text = "|".join(frame.frame_hash for frame in frames); digest = sha256(text.encode("utf-8")).hexdigest()
        run_id = _run_id(timeline, config)
        return ReplayRun(REPLAY_RUNNER_VERSION, REPLAY_FRAME_VERSION, timeline.scenario_id, timeline.timeline_version, timeline.deterministic_hash, run_id, timeline.start_at, timeline.end_at, timeline.timezone, timeline.event_count, len(frames), frames[0].frame_sequence if frames else None, frames[-1].frame_sequence if frames else None, frames, digest, not blocked, "blocked" if blocked else "completed", (), ("stopped_by_policy",) if blocked else (), stopped.source_event_id if stopped else None, stopped.source_event_sequence if stopped else None, {})
    except (TypeError, ValueError):
        return ReplayRun(REPLAY_RUNNER_VERSION, REPLAY_FRAME_VERSION, timeline.scenario_id, timeline.timeline_version, timeline.deterministic_hash, "", timeline.start_at, timeline.end_at, timeline.timezone, timeline.event_count, 0, None, None, (), "", False, "blocked", (), ("runner_failure",), None, None, {})
