"""Typed results for deterministic evaluation of an immutable ReplayFrame."""
from __future__ import annotations
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Mapping
from .frame import ReplayFrame
from .input_contract import ReplayTimeframe

REPLAY_EVALUATION_CONTRACT_VERSION = "1.0"

class ReplayEngineEvaluationState(StrEnum):
    EVALUATED="evaluated"; SKIPPED="skipped"; UNAVAILABLE="unavailable"; STALE="stale"; INVALID="invalid"; FAILED="failed"
class ReplayReplayEvaluationState(StrEnum):
    EVALUATED="evaluated"; SKIPPED="skipped"; UNAVAILABLE="unavailable"; INVALID="invalid"; FAILED="failed"; BLOCKED="blocked"

@dataclass(frozen=True, slots=True)
class ReplayEvaluationInput:
    evaluation_contract_version: str; scenario_id: str; run_id: str; frame_id: str; frame_sequence: int; occurred_at: object; evaluated_at: object; timezone: str; symbol: str; market: str; session_state: object; timeframe_inputs: Mapping[ReplayTimeframe, Mapping[str, Any] | None]; source_event_id: str; source_event_sequence: int; frame_hash: str; source_lineage: Mapping[str, str]; valid: bool; warnings: tuple[str, ...]; error_codes: tuple[str, ...]

@dataclass(frozen=True, slots=True)
class ReplayEngineEvaluation:
    engine_name: str; engine_version: str; timeframe: ReplayTimeframe; source_frame_id: str; source_snapshot_at: object | None; input_hash: str; output_hash: str | None; evaluation_state: ReplayEngineEvaluationState; valid: bool; output: object | None; warnings: tuple[str, ...]; error_codes: tuple[str, ...]; lineage: Mapping[str, str]

@dataclass(frozen=True, slots=True)
class ReplayDecisionEvaluation:
    decision_input_version: str | None; confidence_version: str | None; risk_version: str | None; next_step_version: str | None; source_frame_id: str; source_frame_hash: str; evaluated_at: object; decision_input_hash: str | None; confidence_hash: str | None; risk_hash: str | None; next_step_hash: str | None; valid: bool; decision_input: object | None; confidence: object | None; risk: object | None; next_step: object | None; warnings: tuple[str, ...]; error_codes: tuple[str, ...]; lineage: Mapping[str, str]

@dataclass(frozen=True, slots=True)
class ReplayEvaluationResult:
    evaluation_contract_version: str; evaluator_adapter_version: str; evaluator_version: str; source_frame_id: str; source_frame_hash: str; evaluation_id: str; evaluation_state: ReplayReplayEvaluationState; evaluated_at: object; engine_evaluations: tuple[ReplayEngineEvaluation, ...]; decision_evaluation: ReplayDecisionEvaluation | None; evaluation_hash: str; valid: bool; warnings: tuple[str, ...]; error_codes: tuple[str, ...]; lineage: Mapping[str, str]

@dataclass(frozen=True, slots=True)
class EvaluatedReplayFrame:
    frame: ReplayFrame; evaluation: ReplayEvaluationResult; evaluated_frame_hash: str; valid: bool; warnings: tuple[str, ...]; error_codes: tuple[str, ...]
