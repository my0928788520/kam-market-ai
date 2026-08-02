"""Formation Research Contract V0.1: manually declared descriptive records only."""
from __future__ import annotations
import hashlib,json,sqlite3
from contextlib import closing
from dataclasses import asdict,dataclass
from datetime import UTC,datetime
from enum import StrEnum
from pathlib import Path
from uuid import uuid4
from .knowledge_contract import KnowledgeContractStore
from .traceability import EvidenceTraceabilityStore,TraceabilityStatus
from .evidence_versioning import EvidenceVersionStore

FORMATION_SCHEMA_VERSION='FORMATION_RESEARCH_CONTRACT_SCHEMA_V0_1'
class FormationType(StrEnum):SEQUENTIAL_FORMATION='SEQUENTIAL_FORMATION';LEAD_LAG_FORMATION='LEAD_LAG_FORMATION';PERSISTENCE_FORMATION='PERSISTENCE_FORMATION';RELATIONSHIP_SHIFT_FORMATION='RELATIONSHIP_SHIFT_FORMATION';TRANSITION_FORMATION='TRANSITION_FORMATION';COMPOSITE_FORMATION='COMPOSITE_FORMATION';UNSPECIFIED_FORMATION='UNSPECIFIED_FORMATION'
class FormationStatus(StrEnum):FORMING='FORMING';PERSISTING='PERSISTING';BROKEN='BROKEN';INVALIDATED='INVALIDATED';COMPLETED='COMPLETED';UNRESOLVED='UNRESOLVED'
@dataclass(frozen=True,slots=True)
class FormationDraft:
 title:str;statement:str;formation_type:FormationType;formation_status:FormationStatus;source_observation_ids:tuple[str,...]=();source_evidence_ids:tuple[str,...]=();source_knowledge_ids:tuple[str,...]=();transition_events:tuple[dict[str,object],...]=();initial_state:str|None=None;result_state:str|None=None;lead_entities:tuple[str,...]=();lag_entities:tuple[str,...]=();timing_relationships:tuple[dict[str,object],...]=();persistence_state:dict[str,object]|None=None;relationship_changes:tuple[dict[str,object],...]=();invalidation_conditions:tuple[dict[str,object],...]=()
@dataclass(frozen=True,slots=True)
class FormationRecord:
 formation_id:str;formation_family_id:str;formation_version:int;previous_formation_id:str|None;title:str;statement:str;formation_type:FormationType;formation_status:FormationStatus;source_observation_ids:tuple[str,...];source_evidence_ids:tuple[str,...];source_knowledge_ids:tuple[str,...];transition_events:tuple[dict[str,object],...];initial_state:str|None;result_state:str|None;lead_entities:tuple[str,...];lag_entities:tuple[str,...];timing_relationships:tuple[dict[str,object],...];persistence_state:dict[str,object]|None;relationship_changes:tuple[dict[str,object],...];invalidation_conditions:tuple[dict[str,object],...];created_at:str;schema_version:str=FORMATION_SCHEMA_VERSION
 def payload(self):
  x=asdict(self);x['formation_type']=self.formation_type.value;x['formation_status']=self.formation_status.value;return x
def formation_family_id(d:FormationDraft,knowledge_scope:tuple[str,...],evidence_scope:tuple[str,...])->str:
 structural={'entities':sorted(set(d.lead_entities+d.lag_entities)),'transition_entities':[e.get('entity') for e in sorted(d.transition_events,key=lambda e:e['sequence_index'])]}
 raw={'type':d.formation_type.value,'statement':' '.join(d.statement.split()),'knowledge_scope':sorted(knowledge_scope),'evidence_scope':sorted(evidence_scope),'structure':structural}
 return hashlib.sha256(json.dumps(raw,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()
class FormationStore:
 def __init__(self,path:str|Path):self.path=Path(path);self.knowledge=KnowledgeContractStore(path);self.traces=EvidenceTraceabilityStore(path);self.evidence=EvidenceVersionStore(path)
 def _observation_exists(self,oid):
  with closing(sqlite3.connect(self.path)) as db:rows=db.execute("SELECT payload_json FROM observations WHERE category='OBSERVATION_V0_1'").fetchall()
  return any(json.loads(r[0]).get('observation_id')==oid for r in rows)
 def append(self,d:FormationDraft)->FormationRecord:
  if not d.title.strip() or not d.statement.strip():raise ValueError('Formation title and statement are required.')
  if not (d.source_observation_ids or d.source_evidence_ids or d.source_knowledge_ids):raise ValueError('At least one exact source is required.')
  if any(not self._observation_exists(x) for x in d.source_observation_ids):raise LookupError('Pinned Observation was not found.')
  for x in d.source_evidence_ids:
   t=self.traces.get(x)
   if t is None:raise LookupError('Pinned Evidence was not found.')
   if t.status is not TraceabilityStatus.COMPLETE:raise ValueError('Pinned Evidence is not traceable.')
  ks=[]
  for x in d.source_knowledge_ids:
   k=self.knowledge.get(x)
   if k is None:raise LookupError('Pinned Knowledge was not found.')
   ks.append(k)
  groups=(d.source_observation_ids,d.source_evidence_ids,d.source_knowledge_ids)
  if any(len(set(group))!=len(group) for group in groups):raise ValueError('Duplicate source semantics are not permitted.')
  required_event={'sequence_index','entity','event_type','state_before','state_after','observed_at','source_observation_ids','notes'}
  if not d.transition_events or any(set(event)!=required_event for event in d.transition_events) or any(event.get('sequence_index')!=i for i,event in enumerate(d.transition_events)) or any(not self._observation_exists(x) for event in d.transition_events for x in event.get('source_observation_ids',())):raise ValueError('Transition sequence or source Observation is invalid.')
  valid_units={'MILLISECONDS','SECONDS','BARS','EVENTS','UNSPECIFIED'};valid_basis={'EXCHANGE_EVENT_TIME','SEQUENCE_INDEX','BAR_DISTANCE','OBSERVED_ORDER','UNSPECIFIED'}
  if any(item.get('delay_unit') not in valid_units or item.get('basis') not in valid_basis for item in d.timing_relationships):raise ValueError('Timing relationship is invalid.')
  if d.persistence_state and d.persistence_state.get('classification') not in {'PERSISTENT','INTERMITTENT','TRANSIENT','UNKNOWN'}:raise ValueError('Persistence state is invalid.')
  if d.formation_status is FormationStatus.INVALIDATED and not d.invalidation_conditions:raise ValueError('INVALIDATED requires a declared condition.')
  evidence_scope=[]
  for evidence_id in d.source_evidence_ids:
   version=self.evidence.get(evidence_id)
   if version is None:raise LookupError('Pinned Evidence was not found.')
   evidence_scope.append(version.evidence_family_id)
  family=formation_family_id(d,tuple(k.knowledge_family_id for k in ks),tuple(evidence_scope))
  with closing(sqlite3.connect(self.path)) as db:
   last=db.execute('SELECT formation_id,formation_version FROM formation_records WHERE formation_family_id=? ORDER BY formation_version DESC LIMIT 1',(family,)).fetchone();version,prev=((last[1]+1),last[0]) if last else (1,None);r=FormationRecord(str(uuid4()),family,version,prev,d.title,d.statement,d.formation_type,d.formation_status,tuple(sorted(d.source_observation_ids)),tuple(sorted(d.source_evidence_ids)),tuple(sorted(d.source_knowledge_ids)),d.transition_events,d.initial_state,d.result_state,d.lead_entities,d.lag_entities,d.timing_relationships,d.persistence_state,d.relationship_changes,d.invalidation_conditions,datetime.now(UTC).isoformat())
   db.execute('INSERT INTO formation_records(formation_id,formation_family_id,formation_version,previous_formation_id,payload_json,created_at) VALUES(?,?,?,?,?,?)',(r.formation_id,family,version,prev,json.dumps(r.payload(),ensure_ascii=False),r.created_at));db.commit()
  return r
 def get(self,formation_id:str)->FormationRecord|None:
  with closing(sqlite3.connect(self.path)) as db:row=db.execute('SELECT payload_json FROM formation_records WHERE formation_id=?',(formation_id,)).fetchone()
  if not row:return None
  data=json.loads(row[0]);data['formation_type']=FormationType(data['formation_type']);data['formation_status']=FormationStatus(data['formation_status'])
  for name in ('source_observation_ids','source_evidence_ids','source_knowledge_ids','transition_events','lead_entities','lag_entities','timing_relationships','relationship_changes','invalidation_conditions'):data[name]=tuple(data[name])
  for name in ('transition_events','timing_relationships','relationship_changes'):
   data[name]=tuple({**item,'source_observation_ids':tuple(item['source_observation_ids'])} if 'source_observation_ids' in item else item for item in data[name])
  return FormationRecord(**data)
 def history(self,family_id:str)->list[FormationRecord]:
  with closing(sqlite3.connect(self.path)) as db:ids=[row[0] for row in db.execute('SELECT formation_id FROM formation_records WHERE formation_family_id=? ORDER BY formation_version ASC',(family_id,))]
  return [record for formation_id in ids if (record:=self.get(formation_id))]
 def latest(self,family_id:str)->FormationRecord|None:
  rows=self.history(family_id);return rows[-1] if rows else None
