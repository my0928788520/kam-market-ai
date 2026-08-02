"""空明 KAM｜Evidence Comparison V0.1 — structural descriptive diffs only."""
from __future__ import annotations
import json,sqlite3
from contextlib import closing
from dataclasses import asdict,dataclass
from datetime import UTC,datetime
from pathlib import Path
from uuid import uuid4
from .evidence_versioning import EvidenceVersionStore,VersionedEvidence
@dataclass(frozen=True,slots=True)
class EvidenceComparison:
 comparison_id:str;evidence_family_id:str;base_evidence_id:str;base_evidence_version:int;target_evidence_id:str;target_evidence_version:int;compared_at:datetime;observation_count_before:int;observation_count_after:int;observation_count_delta:int;observation_time_start_before:str|None;observation_time_start_after:str|None;observation_time_end_before:str|None;observation_time_end_after:str|None;aggregation_method_before:str;aggregation_method_after:str;schema_version_before:str;schema_version_after:str;source_query_equal:bool;payload_diff:dict[str,object];comparison_schema_version:str='EVIDENCE_COMPARISON_SCHEMA_V0_1'
 def payload(self):
  x=asdict(self);x['compared_at']=self.compared_at.isoformat();return x
class EvidenceComparisonStore:
 def __init__(self,path:str|Path):self.path=Path(path);self.versions=EvidenceVersionStore(path)
 def compare(self,base_id:str,target_id:str)->EvidenceComparison:
  b=self.versions.get(base_id);t=self.versions.get(target_id)
  if not b or not t:raise LookupError('evidence missing')
  if b.evidence_family_id!=t.evidence_family_id:raise ValueError('different evidence family')
  if b.evidence_version>=t.evidence_version:raise ValueError('invalid version order')
  d=self._diff(b.payload,t.payload);bc=int(b.payload['observation_count']);tc=int(t.payload['observation_count'])
  return EvidenceComparison(str(uuid4()),b.evidence_family_id,b.evidence_id,b.evidence_version,t.evidence_id,t.evidence_version,datetime.now(UTC),bc,tc,tc-bc,b.payload.get('first_exchange_event_at'),t.payload.get('first_exchange_event_at'),b.payload.get('last_exchange_event_at'),t.payload.get('last_exchange_event_at'),'QUERY_AGGREGATION','QUERY_AGGREGATION',b.schema_version,t.schema_version,b.payload.get('criteria')==t.payload.get('criteria'),d)
 def save(self,c:EvidenceComparison)->None:
  with closing(sqlite3.connect(self.path)) as db:db.execute('INSERT INTO evidence_comparisons(comparison_id,payload_json,created_at) VALUES(?,?,?)',(c.comparison_id,json.dumps(c.payload(),ensure_ascii=False),c.compared_at.isoformat()));db.commit()
 def get(self,comparison_id:str)->dict[str,object]|None:
  with closing(sqlite3.connect(self.path)) as db:r=db.execute('SELECT payload_json FROM evidence_comparisons WHERE comparison_id=?',(comparison_id,)).fetchone()
  return json.loads(r[0]) if r else None
 def find(self,base_id:str,target_id:str)->dict[str,object]|None:
  with closing(sqlite3.connect(self.path)) as db: rows=db.execute('SELECT payload_json FROM evidence_comparisons').fetchall()
  return next((json.loads(r[0]) for r in rows if json.loads(r[0]).get('base_evidence_id')==base_id and json.loads(r[0]).get('target_evidence_id')==target_id),None)
 @staticmethod
 def _diff(a:dict[str,object],b:dict[str,object])->dict[str,object]:
  return {'added':{k:b[k] for k in b.keys()-a.keys()},'removed':{k:a[k] for k in a.keys()-b.keys()},'changed':{k:{'before':a[k],'after':b[k]} for k in a.keys()&b.keys() if a[k]!=b[k]}}
