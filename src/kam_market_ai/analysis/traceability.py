"""空明 KAM｜Evidence Traceability V0.1 — data lineage checks only."""
from __future__ import annotations
import json,sqlite3
from contextlib import closing
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from ..storage.observation_query import ObservationQueryStore
from .evidence_contracts import CriteriaCanonicalCodec, EVIDENCE_AGGREGATION_METHOD, EVIDENCE_SCHEMA_VERSION

class TraceabilityStatus(StrEnum): COMPLETE='COMPLETE';COUNT_MISMATCH='COUNT_MISMATCH';SOURCE_OBSERVATION_MISSING='SOURCE_OBSERVATION_MISSING';QUERY_INVALID='QUERY_INVALID';UNKNOWN='UNKNOWN'
@dataclass(frozen=True,slots=True)
class EvidenceTrace:
    evidence_id:str;evidence_type:str;source_query:dict[str,object];observation_count:int;observation_time_start:str|None;observation_time_end:str|None;aggregation_method:str;evidence_schema_version:str;status:TraceabilityStatus;replay_count:int
class EvidenceTraceabilityStore:
    def __init__(self,path:str|Path):self.path=Path(path);self._queries=ObservationQueryStore(path)
    def get(self,evidence_id:str)->EvidenceTrace|None:
        with closing(sqlite3.connect(self.path)) as db: row=db.execute('SELECT evidence_type,payload_json FROM descriptive_evidence WHERE evidence_id=?',(evidence_id,)).fetchone()
        if not row:return None
        try:
            p=json.loads(row[1]); c=CriteriaCanonicalCodec.canonical_payload(p['criteria']); q=CriteriaCanonicalCodec.to_query(c)
            replay=len(self._queries.query(q)); expected=int(p['observation_count']); status=TraceabilityStatus.COMPLETE if replay==expected else (TraceabilityStatus.SOURCE_OBSERVATION_MISSING if replay==0 and expected>0 else TraceabilityStatus.COUNT_MISMATCH)
            return EvidenceTrace(evidence_id,row[0],c,expected,p.get('first_exchange_event_at'),p.get('last_exchange_event_at'),EVIDENCE_AGGREGATION_METHOD,EVIDENCE_SCHEMA_VERSION,status,replay)
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):return EvidenceTrace(evidence_id,row[0],{},0,None,None,EVIDENCE_AGGREGATION_METHOD,EVIDENCE_SCHEMA_VERSION,TraceabilityStatus.QUERY_INVALID,0)
