"""Append-only shadow observations and outcome summaries for Quality Gate V1."""
from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from .quality_gate import QualityGateResult


@dataclass(frozen=True, slots=True)
class ShadowObservation:
    observation_id: str
    evaluated_at: datetime
    instrument: str
    session: str
    decision: str
    score: Decimal
    passed_conditions: int
    total_conditions: int
    supports: tuple[str, ...]
    blockers: tuple[str, ...]
    entry_price: Decimal | None = None
    exit_price: Decimal | None = None
    outcome_points: Decimal | None = None
    costs_points: Decimal = Decimal(0)

    @classmethod
    def from_result(cls, observation_id: str, instrument: str, session: str, result: QualityGateResult) -> ShadowObservation:
        return cls(observation_id, result.evaluated_at, instrument, session, result.decision.value, result.score, result.passed_conditions, result.total_conditions, tuple(x.value for x in result.supports), tuple(x.value for x in result.blockers))


def append_observation(path: Path, observation: ShadowObservation) -> None:
    """Append one JSON line; the caller controls the local research path."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = asdict(observation)
    payload["evaluated_at"] = observation.evaluated_at.isoformat()
    for key in ("score", "entry_price", "exit_price", "outcome_points", "costs_points"):
        payload[key] = None if payload[key] is None else str(payload[key])
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")


def summarize_outcomes(observations: Iterable[ShadowObservation]) -> dict[str, object]:
    """Report win rate and expectancy only for completed A-grade observations."""
    completed = [item for item in observations if item.decision == "a_grade" and item.outcome_points is not None]
    wins = [item for item in completed if item.outcome_points - item.costs_points > 0]
    losses = [item for item in completed if item.outcome_points - item.costs_points <= 0]
    net = sum((item.outcome_points - item.costs_points for item in completed), Decimal(0))
    return {
        "sample_size": len(completed),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": None if not completed else (Decimal(len(wins)) / Decimal(len(completed)) * Decimal(100)).quantize(Decimal(".01")),
        "net_points": net,
        "expectancy_points": None if not completed else (net / Decimal(len(completed))).quantize(Decimal(".01")),
        "adjustment_allowed": len(completed) >= 30,
    }
