"""空明 KAM｜Evidence Versioning V0.1 — append-only descriptive snapshots."""
from __future__ import annotations
import json,sqlite3
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4
from .evidence import DescriptiveEvidenceSnapshot

@dataclass(frozen=True,slots=True)
class VersionedEvidence:
    evidence_id:str;evidence_family_id:str;evidence_version:int;previous_evidence_id:str|None;generated_at:str;schema_version:str;payload:dict[str,object]
class EvidenceVersionStore:
    def __init__(self,path:str|Path):self.path=Path(path)
    def append(self,snapshot:DescriptiveEvidenceSnapshot,family_id:str,previous_evidence_id:str|None=None)->VersionedEvidence:
        with sqlite3.connect(self.path) as db:
            row=db.execute('SELECT evidence_id,evidence_version FROM descriptive_evidence WHERE evidence_family_id=? ORDER BY evidence_version DESC LIMIT 1',(family_id,)).fetchone(); version=(row[1]+1) if row else 1; previous=row[0] if row else None
            if previous_evidence_id is not None and previous_evidence_id!=previous:raise ValueError('previous evidence does not match family latest')
            eid=str(uuid4());payload=snapshot.payload();db.execute('INSERT INTO descriptive_evidence(evidence_id,evidence_type,payload_json,created_at,evidence_family_id,evidence_version,previous_evidence_id,schema_version) VALUES(?,?,?,?,?,?,?,?)',(eid,snapshot.evidence_type,json.dumps(payload),snapshot.created_at.isoformat(),family_id,version,previous,'DESCRIPTIVE_EVIDENCE_SCHEMA_V0_1'));db.commit()
            return VersionedEvidence(eid,family_id,version,previous,snapshot.created_at.isoformat(),'DESCRIPTIVE_EVIDENCE_SCHEMA_V0_1',payload)
    def get(self,evidence_id:str)->VersionedEvidence|None:
        with sqlite3.connect(self.path) as db:r=db.execute('SELECT evidence_id,evidence_family_id,evidence_version,previous_evidence_id,created_at,schema_version,payload_json FROM descriptive_evidence WHERE evidence_id=?',(evidence_id,)).fetchone()
        return VersionedEvidence(r[0],r[1],r[2],r[3],r[4],r[5],json.loads(r[6])) if r else None
    def history(self,family_id:str)->list[VersionedEvidence]:
        with sqlite3.connect(self.path) as db:ids=[r[0] for r in db.execute('SELECT evidence_id FROM descriptive_evidence WHERE evidence_family_id=? ORDER BY evidence_version ASC',(family_id,))]
        return [self.get(x) for x in ids if self.get(x)]
    def latest(self,family_id:str)->VersionedEvidence|None:
        h=self.history(family_id);return h[-1] if h else None
