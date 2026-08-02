"""空明 KAM｜Evidence Change Timeline V0.1 — descriptive version chronology."""
from __future__ import annotations
import json,sqlite3
from contextlib import closing
from dataclasses import asdict,dataclass
from datetime import UTC,datetime
from pathlib import Path
from uuid import uuid4
from .evidence_comparison import EvidenceComparisonStore
from .evidence_versioning import EvidenceVersionStore
@dataclass(frozen=True,slots=True)
class TimelineEntry:
 evidence_id:str;evidence_version:int;previous_evidence_id:str|None;generated_at:str;observation_count:int;observation_time_start:str|None;observation_time_end:str|None;aggregation_method:str;schema_version:str;comparison_from_previous:dict[str,object]|None
@dataclass(frozen=True,slots=True)
class EvidenceChangeTimeline:
 timeline_id:str;evidence_family_id:str;generated_at:datetime;timeline_schema_version:str;version_count:int;first_evidence_id:str;first_evidence_version:int;latest_evidence_id:str;latest_evidence_version:int;timeline_entries:tuple[TimelineEntry,...];summary:dict[str,object]
 def payload(self):x=asdict(self);x['generated_at']=self.generated_at.isoformat();return x
class EvidenceTimelineStore:
 def __init__(self,path:str|Path):self.path=Path(path);self.versions=EvidenceVersionStore(path);self.comparisons=EvidenceComparisonStore(path)
 def build(self,family:str)->EvidenceChangeTimeline:
  h=self.versions.history(family)
  if not h:raise LookupError('family missing')
  entries=[];changes={};adds={};removes={}
  for i,v in enumerate(h):
   comp=None
   if i:
    comp=self.comparisons.find(h[i-1].evidence_id,v.evidence_id)
    if comp is None:
     c=self.comparisons.compare(h[i-1].evidence_id,v.evidence_id);self.comparisons.save(c);comp=c.payload()
    diff=comp['payload_diff'];changes[f'{h[i-1].evidence_version}->{v.evidence_version}']=list(diff['changed']);adds[f'{h[i-1].evidence_version}->{v.evidence_version}']=list(diff['added']);removes[f'{h[i-1].evidence_version}->{v.evidence_version}']=list(diff['removed'])
   p=v.payload;entries.append(TimelineEntry(v.evidence_id,v.evidence_version,v.previous_evidence_id,v.generated_at,int(p['observation_count']),p.get('first_exchange_event_at'),p.get('last_exchange_event_at'),'QUERY_AGGREGATION',v.schema_version,comp))
  return EvidenceChangeTimeline(str(uuid4()),family,datetime.now(UTC),'EVIDENCE_CHANGE_TIMELINE_SCHEMA_V0_1',len(h),h[0].evidence_id,h[0].evidence_version,h[-1].evidence_id,h[-1].evidence_version,tuple(entries),{'observation_count_first':entries[0].observation_count,'observation_count_latest':entries[-1].observation_count,'observation_count_total_delta':entries[-1].observation_count-entries[0].observation_count,'changed_field_names_by_transition':changes,'added_field_names_by_transition':adds,'removed_field_names_by_transition':removes})
 def save(self,t:EvidenceChangeTimeline)->None:
  with closing(sqlite3.connect(self.path)) as db:db.execute('CREATE TABLE IF NOT EXISTS evidence_change_timelines (timeline_id TEXT PRIMARY KEY,payload_json TEXT NOT NULL,created_at TEXT NOT NULL)');db.execute('INSERT INTO evidence_change_timelines(timeline_id,payload_json,created_at) VALUES(?,?,?)',(t.timeline_id,json.dumps(t.payload(),ensure_ascii=False),t.generated_at.isoformat()));db.commit()
 def get(self,timeline_id:str)->dict[str,object]|None:
  with closing(sqlite3.connect(self.path)) as db:r=db.execute('SELECT payload_json FROM evidence_change_timelines WHERE timeline_id=?',(timeline_id,)).fetchone()
  return json.loads(r[0]) if r else None
