"""SQLite persistence for reproducible Shadow observations."""
from __future__ import annotations
import json, sqlite3
from contextlib import closing
from dataclasses import asdict
from pathlib import Path
from ..execution.shadow import ShadowTrade
from ..analysis.reaction_chain import ReactionAnalysis
from ..analysis.observation import Observation
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from ..analysis.evidence import DescriptiveEvidenceSnapshot

class ShadowStore:
    def __init__(self, path: str | Path) -> None: self.path=Path(path)
    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True,exist_ok=True)
        with closing(sqlite3.connect(self.path)) as db:
            db.execute("""CREATE TABLE IF NOT EXISTS shadow_trades (
                id TEXT PRIMARY KEY, instrument TEXT NOT NULL, side TEXT NOT NULL,
                entry_time TEXT NOT NULL, payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)""")
            db.execute("""CREATE TABLE IF NOT EXISTS observations (
                id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp TEXT NOT NULL,
                category TEXT NOT NULL, payload_json TEXT NOT NULL)""")
            db.execute("""CREATE TABLE IF NOT EXISTS descriptive_evidence (
                evidence_id TEXT PRIMARY KEY, evidence_type TEXT NOT NULL,
                payload_json TEXT NOT NULL, created_at TEXT NOT NULL)""")
            for column, definition in (("evidence_family_id","TEXT"),("evidence_version","INTEGER"),("previous_evidence_id","TEXT"),("schema_version","TEXT")):
                try: db.execute(f"ALTER TABLE descriptive_evidence ADD COLUMN {column} {definition}")
                except sqlite3.OperationalError: pass
            db.execute("CREATE TABLE IF NOT EXISTS evidence_comparisons (comparison_id TEXT PRIMARY KEY, payload_json TEXT NOT NULL, created_at TEXT NOT NULL)")
            db.execute("CREATE TABLE IF NOT EXISTS evidence_change_timelines (timeline_id TEXT PRIMARY KEY, payload_json TEXT NOT NULL, created_at TEXT NOT NULL)")
            db.execute("CREATE TABLE IF NOT EXISTS knowledge_records (knowledge_id TEXT PRIMARY KEY, knowledge_family_id TEXT NOT NULL, knowledge_version INTEGER NOT NULL, previous_knowledge_id TEXT, payload_json TEXT NOT NULL, created_at TEXT NOT NULL)")
            db.execute("CREATE TABLE IF NOT EXISTS knowledge_conflicts (conflict_id TEXT PRIMARY KEY, conflict_family_id TEXT NOT NULL, conflict_version INTEGER NOT NULL, previous_conflict_id TEXT, payload_json TEXT NOT NULL, created_at TEXT NOT NULL)")
            db.execute("CREATE TABLE IF NOT EXISTS formation_records (formation_id TEXT PRIMARY KEY, formation_family_id TEXT NOT NULL, formation_version INTEGER NOT NULL, previous_formation_id TEXT, payload_json TEXT NOT NULL, created_at TEXT NOT NULL)")
            db.execute("CREATE TABLE IF NOT EXISTS formation_invalidations (invalidation_id TEXT PRIMARY KEY, invalidation_family_id TEXT NOT NULL, invalidation_version INTEGER NOT NULL, previous_invalidation_id TEXT, formation_id TEXT NOT NULL, payload_json TEXT NOT NULL, created_at TEXT NOT NULL)")
            db.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_descriptive_evidence_family_version ON descriptive_evidence(evidence_family_id, evidence_version) WHERE evidence_family_id IS NOT NULL AND evidence_version IS NOT NULL")
            db.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_knowledge_family_version ON knowledge_records(knowledge_family_id, knowledge_version)")
            db.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_conflict_family_version ON knowledge_conflicts(conflict_family_id, conflict_version)")
            db.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_formation_family_version ON formation_records(formation_family_id, formation_version)")
            db.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_invalidation_family_version ON formation_invalidations(invalidation_family_id, invalidation_version)")
            db.commit()
    def save_trade(self, trade: ShadowTrade) -> None:
        payload=asdict(trade)
        for key,value in tuple(payload.items()):
            if hasattr(value,"isoformat"): payload[key]=value.isoformat()
            elif hasattr(value,"value"): payload[key]=value.value
        with closing(sqlite3.connect(self.path)) as db:
            db.execute("INSERT OR REPLACE INTO shadow_trades(id,instrument,side,entry_time,payload_json) VALUES(?,?,?,?,?)",
                       (trade.id,trade.instrument.value,trade.side.value,trade.entry_time.isoformat(),json.dumps(payload,ensure_ascii=False)))
            db.commit()
    def append_observation(self, timestamp: str, category: str, payload: dict[str,object]) -> None:
        with closing(sqlite3.connect(self.path)) as db:
            db.execute("INSERT INTO observations(timestamp,category,payload_json) VALUES(?,?,?)",
                       (timestamp,category,json.dumps(payload,ensure_ascii=False,default=str)))
            db.commit()

    def save_reaction_analysis(self, analysis: ReactionAnalysis, observed_at: str) -> None:
        """Persist descriptive reaction observations; this never creates a trade."""
        self.append_observation(observed_at, "REACTION_CHAIN_V0_2", analysis.storage_payload())

    def save_observation(self, observation: Observation) -> None:
        self.append_observation(observation.created_at.isoformat(), "OBSERVATION_V0_1", observation.payload())

    def save_descriptive_evidence(self, evidence: "DescriptiveEvidenceSnapshot") -> object:
        """Legacy compatibility entry point delegated to the official history boundary."""
        from ..analysis.evidence_versioning import EvidenceVersionStore
        return EvidenceVersionStore(self.path).append(evidence)
