"""Explicit immutable callables for the existing Decision layer."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Callable, Mapping

@dataclass(frozen=True, slots=True)
class FrozenDecisionCallableBundle:
    bundle_version: str
    decision_input_builder: Callable[..., object]
    confidence_callable: Callable[[object], object]
    risk_callable: Callable[[object, object], object]
    next_step_callable: Callable[[object, object, object], object]
    decision_input_version: str
    confidence_version: str
    risk_version: str
    next_step_version: str
    lineage: Mapping[str, str]
    valid: bool = True

    def __post_init__(self) -> None:
        if self.bundle_version != "1.0" or not self.valid:
            raise ValueError("A valid frozen Decision bundle version 1.0 is required")
        if not all(callable(value) for value in (self.decision_input_builder, self.confidence_callable, self.risk_callable, self.next_step_callable)):
            raise TypeError("Frozen Decision bundle requires four explicit callables")
        if not all(isinstance(value, str) and value for value in (self.decision_input_version, self.confidence_version, self.risk_version, self.next_step_version)):
            raise ValueError("Frozen Decision bundle requires non-empty versions")
