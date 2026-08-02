"""Protocol and frozen callable bundle for Replay evaluation adapters."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Callable, Protocol
from .evaluation_contract import ReplayEvaluationInput, ReplayEvaluationResult

class ReplayEvaluator(Protocol):
    @property
    def evaluator_version(self) -> str: ...
    def evaluate(self, frame_input: ReplayEvaluationInput) -> ReplayEvaluationResult: ...

@dataclass(frozen=True, slots=True)
class FrozenEngineBundle:
    position: Callable[[object, object], object]
    trend: Callable[[object, object], object]
    structure: Callable[[object, object], object]
    timing: Callable[[object, object], object]
    engine_versions: dict[str, str]
