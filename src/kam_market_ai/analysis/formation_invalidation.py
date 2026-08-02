"""Formation Invalidation Boundary V0.1: descriptive research records only.

An invalidation records a research assessment of a pinned Formation.  It does
not mutate the Formation, create a trading action, or decide market direction.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import closing
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from uuid import uuid4

from .formation_contract import FormationStore
from .knowledge_contract import KnowledgeContractStore
from .traceability import EvidenceTraceabilityStore, TraceabilityStatus

INVALIDATION_SCHEMA_VERSION = "FORMATION_INVALIDATION_BOUNDARY_SCHEMA_V0_1"


class InvalidationType(StrEnum):
    STATE_DISAPPEARED = "STATE_DISAPPEARED"
    SEQUENCE_BROKEN = "SEQUENCE_BROKEN"
    TIMING_BOUNDARY_EXCEEDED = "TIMING_BOUNDARY_EXCEEDED"
    RELATIONSHIP_CHANGED = "RELATIONSHIP_CHANGED"
    PERSISTENCE_LOST = "PERSISTENCE_LOST"
    SOURCE_CONTRADICTION = "SOURCE_CONTRADICTION"
    COMPOSITE_INVALIDATION = "COMPOSITE_INVALIDATION"
    MANUAL_RESEARCH_INVALIDATION = "MANUAL_RESEARCH_INVALIDATION"
    UNSPECIFIED_INVALIDATION = "UNSPECIFIED_INVALIDATION"


class InvalidationStatus(StrEnum):
    PENDING_ASSESSMENT = "PENDING_ASSESSMENT"
    CONFIRMED_INVALIDATED = "CONFIRMED_INVALIDATED"
    NOT_INVALIDATED = "NOT_INVALIDATED"
    INCONCLUSIVE = "INCONCLUSIVE"
    REVISED = "REVISED"
    RETIRED = "RETIRED"


class AssessmentMethod(StrEnum):
    MANUAL_REVIEW = "MANUAL_REVIEW"
    CONDITION_REPLAY = "CONDITION_REPLAY"
    SOURCE_COMPARISON = "SOURCE_COMPARISON"
    SEQUENCE_REVIEW = "SEQUENCE_REVIEW"
    TIMING_REVIEW = "TIMING_REVIEW"
    RELATIONSHIP_REVIEW = "RELATIONSHIP_REVIEW"
    PERSISTENCE_REVIEW = "PERSISTENCE_REVIEW"
    UNSPECIFIED_REVIEW = "UNSPECIFIED_REVIEW"


@dataclass(frozen=True, slots=True)
class FormationInvalidationDraft:
    formation_id: str
    invalidation_type: InvalidationType
    invalidation_status: InvalidationStatus
    statement: str
    condition_ids: tuple[str, ...]
    trigger_observation_ids: tuple[str, ...] = ()
    trigger_evidence_ids: tuple[str, ...] = ()
    trigger_knowledge_ids: tuple[str, ...] = ()
    detected_at: datetime | None = None
    effective_sequence_index: int | None = None
    assessment_method: AssessmentMethod = AssessmentMethod.UNSPECIFIED_REVIEW
    research_notes: str | None = None


@dataclass(frozen=True, slots=True)
class FormationInvalidationRecord:
    invalidation_id: str
    invalidation_family_id: str
    invalidation_version: int
    previous_invalidation_id: str | None
    formation_id: str
    formation_family_id: str
    invalidation_type: InvalidationType
    invalidation_status: InvalidationStatus
    statement: str
    condition_ids: tuple[str, ...]
    trigger_observation_ids: tuple[str, ...]
    trigger_evidence_ids: tuple[str, ...]
    trigger_knowledge_ids: tuple[str, ...]
    detected_at: str | None
    effective_sequence_index: int | None
    assessment_method: AssessmentMethod
    research_notes: str | None
    created_at: str
    schema_version: str = INVALIDATION_SCHEMA_VERSION

    def payload(self) -> dict[str, object]:
        data = asdict(self)
        data["invalidation_type"] = self.invalidation_type.value
        data["invalidation_status"] = self.invalidation_status.value
        data["assessment_method"] = self.assessment_method.value
        return data


def invalidation_family_id(draft: FormationInvalidationDraft, formation: object) -> str:
    conditions = {item["condition_id"]: item for item in formation.invalidation_conditions}
    condition_scope = [conditions[item] for item in sorted(draft.condition_ids)]
    semantic = {
        "formation_family_id": formation.formation_family_id,
        "formation_type": formation.formation_type.value,
        "condition_scope": condition_scope,
        "invalidation_type": draft.invalidation_type.value,
        "statement": " ".join(draft.statement.split()),
    }
    return hashlib.sha256(json.dumps(semantic, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")).hexdigest()


class FormationInvalidationStore:
    """Single append-only boundary for manually assessed invalidations."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.formations = FormationStore(path)
        self.knowledge = KnowledgeContractStore(path)
        self.traces = EvidenceTraceabilityStore(path)

    def _validate_observation(self, observation_id: str) -> None:
        if not self.formations._observation_exists(observation_id):
            raise LookupError("Pinned trigger Observation was not found.")

    def _validate_sources(self, draft: FormationInvalidationDraft) -> None:
        groups = (draft.trigger_observation_ids, draft.trigger_evidence_ids, draft.trigger_knowledge_ids)
        if not any(groups):
            raise ValueError("An invalidation requires at least one trigger source.")
        if any(len(set(group)) != len(group) for group in groups):
            raise ValueError("Duplicate trigger source semantics are not permitted.")
        for observation_id in draft.trigger_observation_ids:
            self._validate_observation(observation_id)
        for evidence_id in draft.trigger_evidence_ids:
            trace = self.traces.get(evidence_id)
            if trace is None:
                raise LookupError("Pinned trigger Evidence was not found.")
            if trace.status is not TraceabilityStatus.COMPLETE:
                raise ValueError("Pinned trigger Evidence is not traceable.")
        for knowledge_id in draft.trigger_knowledge_ids:
            knowledge = self.knowledge.get(knowledge_id)
            if knowledge is None:
                raise LookupError("Pinned trigger Knowledge was not found.")
            self.knowledge.traceability_chain(knowledge_id)

    def append(self, draft: FormationInvalidationDraft) -> FormationInvalidationRecord:
        formation = self.formations.get(draft.formation_id)
        if formation is None:
            raise LookupError("Pinned Formation was not found.")
        if not draft.statement.strip() or not draft.condition_ids:
            raise ValueError("Invalidation statement and condition IDs are required.")
        if len(set(draft.condition_ids)) != len(draft.condition_ids):
            raise ValueError("Duplicate condition semantics are not permitted.")
        conditions = {item["condition_id"] for item in formation.invalidation_conditions}
        if not set(draft.condition_ids).issubset(conditions):
            raise ValueError("Invalidation condition is not defined by the pinned Formation.")
        self._validate_sources(draft)
        if draft.effective_sequence_index is not None and not 0 <= draft.effective_sequence_index <= len(formation.transition_events):
            raise ValueError("Effective sequence index is outside the Formation boundary.")
        family = invalidation_family_id(draft, formation)
        with closing(sqlite3.connect(self.path)) as db:
            last = db.execute("SELECT invalidation_id,invalidation_version FROM formation_invalidations WHERE invalidation_family_id=? ORDER BY invalidation_version DESC LIMIT 1", (family,)).fetchone()
            version, previous = ((last[1] + 1), last[0]) if last else (1, None)
            record = FormationInvalidationRecord(
                str(uuid4()), family, version, previous, formation.formation_id,
                formation.formation_family_id, draft.invalidation_type,
                draft.invalidation_status, draft.statement,
                tuple(sorted(draft.condition_ids)), tuple(sorted(draft.trigger_observation_ids)),
                tuple(sorted(draft.trigger_evidence_ids)), tuple(sorted(draft.trigger_knowledge_ids)),
                draft.detected_at.isoformat() if draft.detected_at else None,
                draft.effective_sequence_index, draft.assessment_method,
                draft.research_notes, datetime.now(UTC).isoformat(),
            )
            try:
                db.execute("INSERT INTO formation_invalidations(invalidation_id,invalidation_family_id,invalidation_version,previous_invalidation_id,formation_id,payload_json,created_at) VALUES(?,?,?,?,?,?,?)", (record.invalidation_id, family, version, previous, formation.formation_id, json.dumps(record.payload(), ensure_ascii=False), record.created_at))
                db.commit()
            except sqlite3.IntegrityError as error:
                raise ValueError("Invalid invalidation history.") from error
        return record

    def get(self, invalidation_id: str) -> FormationInvalidationRecord | None:
        with closing(sqlite3.connect(self.path)) as db:
            row = db.execute("SELECT payload_json FROM formation_invalidations WHERE invalidation_id=?", (invalidation_id,)).fetchone()
        if not row:
            return None
        data = json.loads(row[0])
        for name in ("condition_ids", "trigger_observation_ids", "trigger_evidence_ids", "trigger_knowledge_ids"):
            data[name] = tuple(data[name])
        data["invalidation_type"] = InvalidationType(data["invalidation_type"])
        data["invalidation_status"] = InvalidationStatus(data["invalidation_status"])
        data["assessment_method"] = AssessmentMethod(data["assessment_method"])
        return FormationInvalidationRecord(**data)

    def history(self, family_id: str) -> list[FormationInvalidationRecord]:
        with closing(sqlite3.connect(self.path)) as db:
            ids = [row[0] for row in db.execute("SELECT invalidation_id FROM formation_invalidations WHERE invalidation_family_id=? ORDER BY invalidation_version ASC", (family_id,))]
        return [record for invalidation_id in ids if (record := self.get(invalidation_id))]

    def latest(self, family_id: str) -> FormationInvalidationRecord | None:
        history = self.history(family_id)
        return history[-1] if history else None

    def for_formation(self, formation_id: str) -> list[FormationInvalidationRecord]:
        with closing(sqlite3.connect(self.path)) as db:
            ids = [row[0] for row in db.execute("SELECT invalidation_id FROM formation_invalidations WHERE formation_id=? ORDER BY invalidation_family_id ASC,invalidation_version ASC", (formation_id,))]
        return [record for invalidation_id in ids if (record := self.get(invalidation_id))]

    def traceability_chain(self, invalidation_id: str) -> tuple[FormationInvalidationRecord, object, tuple[object, ...]]:
        record = self.get(invalidation_id)
        if record is None:
            raise LookupError("Invalidation record was not found.")
        formation = self.formations.get(record.formation_id)
        triggers = tuple(self.traces.get(evidence_id) for evidence_id in record.trigger_evidence_ids)
        return record, formation, triggers
