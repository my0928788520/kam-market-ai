"""Knowledge Contract V0.1: offline, evidence-pinned records only.

This module deliberately does not infer truth, confidence, rules, predictions,
or decisions.  It validates declared provenance and preserves history.
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

from .traceability import EvidenceTraceabilityStore, TraceabilityStatus

KNOWLEDGE_SCHEMA_VERSION = "KNOWLEDGE_CONTRACT_SCHEMA_V0_1"


class KnowledgeType(StrEnum):
    OBSERVED_KNOWLEDGE = "OBSERVED_KNOWLEDGE"
    INTERPRETED_KNOWLEDGE = "INTERPRETED_KNOWLEDGE"


class KnowledgeStatus(StrEnum):
    DRAFT = "DRAFT"
    CURRENT_UNDERSTANDING = "CURRENT_UNDERSTANDING"
    REVISED = "REVISED"
    RETIRED = "RETIRED"


_BANNED_TERMS = {"BUY", "SELL", "LONG", "SHORT", "ENTRY", "EXIT", "TAKE_PROFIT", "STOP_LOSS", "SIGNAL", "PREDICTION_SCORE", "TRADING_EDGE"}


@dataclass(frozen=True, slots=True)
class KnowledgeDraft:
    knowledge_type: KnowledgeType
    status: KnowledgeStatus
    title: str
    statement: str
    source_evidence_family_ids: tuple[str, ...]
    source_evidence_ids: tuple[str, ...]
    supporting_evidence_ids: tuple[str, ...] = ()
    counter_evidence_ids: tuple[str, ...] = ()
    interpretation: str | None = None
    interpretation_evidence_ids: tuple[str, ...] = ()
    interprets_knowledge_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class KnowledgeRecord:
    knowledge_id: str
    knowledge_family_id: str
    knowledge_version: int
    previous_knowledge_id: str | None
    knowledge_type: KnowledgeType
    status: KnowledgeStatus
    title: str
    statement: str
    source_evidence_family_ids: tuple[str, ...]
    source_evidence_ids: tuple[str, ...]
    supporting_evidence_ids: tuple[str, ...]
    counter_evidence_ids: tuple[str, ...]
    interpretation: str | None
    interpretation_evidence_ids: tuple[str, ...]
    interprets_knowledge_ids: tuple[str, ...]
    created_at: str
    schema_version: str = KNOWLEDGE_SCHEMA_VERSION

    def payload(self) -> dict[str, object]:
        data = asdict(self)
        data["knowledge_type"] = self.knowledge_type.value
        data["status"] = self.status.value
        return data


def knowledge_family_id(draft: KnowledgeDraft, relationship_scope: tuple[str, ...] = ()) -> str:
    """Stable identity of a statement scope, never a measure of validity."""
    identity = {
        "knowledge_type": draft.knowledge_type.value,
        "statement": " ".join(draft.statement.split()),
        "source_evidence_family_ids": sorted(draft.source_evidence_family_ids),
        "interprets_observed_family_scope": sorted(relationship_scope),
    }
    canonical = json.dumps(identity, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class KnowledgeContractStore:
    """Single append-only boundary for offline Knowledge Contract records."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self._traces = EvidenceTraceabilityStore(path)

    def _validate_text(self, *texts: str | None) -> None:
        terms = {term for text in texts if text for term in text.upper().replace("-", "_").split()}
        if terms & _BANNED_TERMS:
            raise ValueError("Knowledge Contract does not permit trading semantics.")

    def _validate_evidence_ids(self, ids: tuple[str, ...], *, required: bool) -> None:
        if required and not ids:
            raise ValueError("Pinned source evidence is required.")
        for evidence_id in ids:
            trace = self._traces.get(evidence_id)
            if trace is None:
                raise LookupError("Pinned evidence was not found.")
            if trace.status is not TraceabilityStatus.COMPLETE:
                raise ValueError("Pinned evidence is not traceable.")

    def _validate(self, draft: KnowledgeDraft) -> None:
        if not draft.title.strip() or not draft.statement.strip():
            raise ValueError("Knowledge title and statement are required.")
        if not draft.source_evidence_family_ids:
            raise ValueError("Source evidence family scope is required.")
        self._validate_text(draft.title, draft.statement, draft.interpretation)
        self._validate_evidence_ids(draft.source_evidence_ids, required=True)
        self._validate_evidence_ids(draft.supporting_evidence_ids, required=False)
        self._validate_evidence_ids(draft.counter_evidence_ids, required=False)
        if draft.knowledge_type is KnowledgeType.OBSERVED_KNOWLEDGE:
            if draft.interpretation is not None or draft.interpretation_evidence_ids or draft.interprets_knowledge_ids:
                raise ValueError("Observed Knowledge must not contain interpretation.")
        else:
            if not draft.interpretation or not draft.interpretation_evidence_ids:
                raise ValueError("Interpreted Knowledge requires interpretation and evidence.")
            self._validate_evidence_ids(draft.interpretation_evidence_ids, required=True)

    def _relationship_scope(self, draft: KnowledgeDraft) -> tuple[str, ...]:
        ids = draft.interprets_knowledge_ids
        if draft.knowledge_type is KnowledgeType.OBSERVED_KNOWLEDGE:
            return ()
        if not ids:
            raise ValueError("Interpreted Knowledge must pin Observed Knowledge.")
        if len(set(ids)) != len(ids):
            raise ValueError("Duplicate Knowledge relationship is not permitted.")
        scopes: list[str] = []
        for knowledge_id in ids:
            target = self.get(knowledge_id)
            if target is None:
                raise LookupError("Pinned Observed Knowledge was not found.")
            if target.knowledge_type is not KnowledgeType.OBSERVED_KNOWLEDGE:
                raise ValueError("Interpreted Knowledge can only reference Observed Knowledge.")
            if target.status is KnowledgeStatus.RETIRED:
                raise ValueError("A retired Observed Knowledge record cannot be newly pinned.")
            scopes.append(target.knowledge_family_id)
        return tuple(sorted(set(scopes)))

    def append(self, draft: KnowledgeDraft) -> KnowledgeRecord:
        self._validate(draft)
        relationship_scope = self._relationship_scope(draft)
        family = knowledge_family_id(draft, relationship_scope)
        with closing(sqlite3.connect(self.path)) as db:
            last = db.execute("SELECT knowledge_id,knowledge_version FROM knowledge_records WHERE knowledge_family_id=? ORDER BY knowledge_version DESC LIMIT 1", (family,)).fetchone()
            version, previous = ((last[1] + 1), last[0]) if last else (1, None)
            record = KnowledgeRecord(str(uuid4()), family, version, previous, draft.knowledge_type, draft.status, draft.title, draft.statement, tuple(draft.source_evidence_family_ids), tuple(draft.source_evidence_ids), tuple(draft.supporting_evidence_ids), tuple(draft.counter_evidence_ids), draft.interpretation, tuple(draft.interpretation_evidence_ids), tuple(draft.interprets_knowledge_ids), datetime.now(UTC).isoformat())
            try:
                db.execute("INSERT INTO knowledge_records(knowledge_id,knowledge_family_id,knowledge_version,previous_knowledge_id,payload_json,created_at) VALUES(?,?,?,?,?,?)", (record.knowledge_id, family, version, previous, json.dumps(record.payload(), ensure_ascii=False), record.created_at))
                db.commit()
            except sqlite3.IntegrityError as error:
                raise ValueError("Invalid Knowledge history.") from error
        return record

    def get(self, knowledge_id: str) -> KnowledgeRecord | None:
        with closing(sqlite3.connect(self.path)) as db:
            row = db.execute("SELECT payload_json FROM knowledge_records WHERE knowledge_id=?", (knowledge_id,)).fetchone()
        if not row:
            return None
        data = json.loads(row[0])
        for name in ("source_evidence_family_ids", "source_evidence_ids", "supporting_evidence_ids", "counter_evidence_ids", "interpretation_evidence_ids", "interprets_knowledge_ids"):
            data[name] = tuple(data[name])
        data["knowledge_type"] = KnowledgeType(data["knowledge_type"])
        data["status"] = KnowledgeStatus(data["status"])
        return KnowledgeRecord(**data)

    def history(self, family_id: str) -> list[KnowledgeRecord]:
        with closing(sqlite3.connect(self.path)) as db:
            ids = [row[0] for row in db.execute("SELECT knowledge_id FROM knowledge_records WHERE knowledge_family_id=? ORDER BY knowledge_version ASC", (family_id,))]
        return [record for knowledge_id in ids if (record := self.get(knowledge_id))]

    def traceability_chain(self, knowledge_id: str) -> tuple[KnowledgeRecord, tuple[object, ...]]:
        record = self.get(knowledge_id)
        if record is None:
            raise LookupError("Knowledge record was not found.")
        evidence_ids = record.source_evidence_ids + record.supporting_evidence_ids + record.counter_evidence_ids + record.interpretation_evidence_ids
        return record, tuple(self._traces.get(evidence_id) for evidence_id in evidence_ids)
