"""Knowledge Conflict Boundary V0.1: declared, descriptive, append-only records."""
from __future__ import annotations
import hashlib,json,sqlite3
from contextlib import closing
from dataclasses import asdict,dataclass
from datetime import UTC,datetime
from enum import StrEnum
from pathlib import Path
from uuid import uuid4
from .knowledge_contract import KnowledgeContractStore,KnowledgeRecord

CONFLICT_SCHEMA_VERSION="KNOWLEDGE_CONFLICT_SCHEMA_V0_1"
class ConflictType(StrEnum):
 DIRECTIONAL_CONFLICT="DIRECTIONAL_CONFLICT";INTERPRETATION_CONFLICT="INTERPRETATION_CONFLICT";SCOPE_CONFLICT="SCOPE_CONFLICT";TEMPORAL_CONFLICT="TEMPORAL_CONFLICT";CONTEXT_CONFLICT="CONTEXT_CONFLICT";UNSPECIFIED_CONFLICT="UNSPECIFIED_CONFLICT"
@dataclass(frozen=True,slots=True)
class KnowledgeConflictDraft:
 knowledge_ids:tuple[str,...];conflict_type:ConflictType;statement:str;context:str|None=None
@dataclass(frozen=True,slots=True)
class KnowledgeConflictRecord:
 conflict_id:str;conflict_family_id:str;conflict_version:int;previous_conflict_id:str|None;knowledge_ids:tuple[str,...];conflict_type:ConflictType;statement:str;context:str|None;created_at:str;schema_version:str=CONFLICT_SCHEMA_VERSION
 def payload(self):
  x=asdict(self);x['conflict_type']=self.conflict_type.value;return x
def conflict_family_id(draft:KnowledgeConflictDraft, knowledge_family_scope:tuple[str,...])->str:
 canonical=json.dumps({'conflict_type':draft.conflict_type.value,'statement':' '.join(draft.statement.split()),'knowledge_family_scope':sorted(knowledge_family_scope)},sort_keys=True,separators=(',',':'),ensure_ascii=False)
 return hashlib.sha256(canonical.encode()).hexdigest()
class KnowledgeConflictStore:
 def __init__(self,path:str|Path):self.path=Path(path);self.knowledge=KnowledgeContractStore(path)
 def _records(self,ids:tuple[str,...])->tuple[KnowledgeRecord,...]:
  if len(ids)<2:raise ValueError('A conflict requires at least two Knowledge records.')
  if len(set(ids))!=len(ids):raise ValueError('Duplicate Knowledge conflict semantics are not permitted.')
  records=[]
  for knowledge_id in ids:
   record=self.knowledge.get(knowledge_id)
   if record is None:raise LookupError('Pinned Knowledge was not found.')
   records.append(record)
  return tuple(records)
 def append(self,draft:KnowledgeConflictDraft)->KnowledgeConflictRecord:
  if not isinstance(draft.conflict_type,ConflictType):raise ValueError('Invalid conflict type.')
  if not draft.statement.strip():raise ValueError('Conflict statement is required.')
  records=self._records(draft.knowledge_ids);canonical_ids=tuple(sorted(draft.knowledge_ids));family=conflict_family_id(draft,tuple(sorted({r.knowledge_family_id for r in records})))
  with closing(sqlite3.connect(self.path)) as db:
   last=db.execute('SELECT conflict_id,conflict_version FROM knowledge_conflicts WHERE conflict_family_id=? ORDER BY conflict_version DESC LIMIT 1',(family,)).fetchone();version,previous=((last[1]+1),last[0]) if last else (1,None);record=KnowledgeConflictRecord(str(uuid4()),family,version,previous,canonical_ids,draft.conflict_type,draft.statement,draft.context,datetime.now(UTC).isoformat())
   try:db.execute('INSERT INTO knowledge_conflicts(conflict_id,conflict_family_id,conflict_version,previous_conflict_id,payload_json,created_at) VALUES(?,?,?,?,?,?)',(record.conflict_id,family,version,previous,json.dumps(record.payload(),ensure_ascii=False),record.created_at));db.commit()
   except sqlite3.IntegrityError as error:raise ValueError('Invalid Conflict history.') from error
  return record
 def get(self,conflict_id:str)->KnowledgeConflictRecord|None:
  with closing(sqlite3.connect(self.path)) as db:r=db.execute('SELECT payload_json FROM knowledge_conflicts WHERE conflict_id=?',(conflict_id,)).fetchone()
  if not r:return None
  p=json.loads(r[0]);p['knowledge_ids']=tuple(p['knowledge_ids']);p['conflict_type']=ConflictType(p['conflict_type']);return KnowledgeConflictRecord(**p)
 def history(self,family_id:str)->list[KnowledgeConflictRecord]:
  with closing(sqlite3.connect(self.path)) as db:ids=[r[0] for r in db.execute('SELECT conflict_id FROM knowledge_conflicts WHERE conflict_family_id=? ORDER BY conflict_version ASC',(family_id,))]
  return [r for i in ids if (r:=self.get(i))]
 def latest(self,family_id:str)->KnowledgeConflictRecord|None:
  rows=self.history(family_id);return rows[-1] if rows else None
 def traceability_chain(self,conflict_id:str):
  record=self.get(conflict_id)
  if record is None:raise LookupError('Conflict record was not found.')
  return record,tuple((self.knowledge.get(k),self.knowledge.traceability_chain(k)[1]) for k in record.knowledge_ids)
