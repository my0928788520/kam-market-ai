"""空明 KAM｜Evidence Versioning V0.1 — immutable append-only history."""
from __future__ import annotations
import hashlib,json,sqlite3
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4
from .evidence import DescriptiveEvidenceSnapshot
from .evidence_contracts import CriteriaCanonicalCodec, EVIDENCE_AGGREGATION_METHOD, EVIDENCE_SCHEMA_VERSION

def evidence_family_id(criteria:dict[str,object], evidence_type:str, aggregation_method:str=EVIDENCE_AGGREGATION_METHOD, schema_identity:str=EVIDENCE_SCHEMA_VERSION)->str:
    canonical=json.dumps({'criteria':CriteriaCanonicalCodec.canonical_payload(criteria),'evidence_type':evidence_type,'aggregation_method':aggregation_method,'schema_identity':schema_identity},sort_keys=True,separators=(',',':'),ensure_ascii=False)
    return hashlib.sha256(canonical.encode()).hexdigest()
@dataclass(frozen=True,slots=True)
class VersionedEvidence:
    evidence_id:str;evidence_family_id:str;evidence_version:int;previous_evidence_id:str|None;generated_at:str;schema_version:str;payload:dict[str,object]
class EvidenceVersionStore:
    def __init__(self,path:str|Path):self.path=Path(path)
    def append(self,snapshot:DescriptiveEvidenceSnapshot)->VersionedEvidence:
        """The sole public append-only Evidence history creation boundary."""
        family_id=evidence_family_id(snapshot.criteria,snapshot.evidence_type)
        with closing(sqlite3.connect(self.path)) as db:
            last=db.execute('SELECT evidence_id,evidence_version FROM descriptive_evidence WHERE evidence_family_id=? ORDER BY evidence_version DESC LIMIT 1',(family_id,)).fetchone();version=(last[1]+1) if last else 1;previous=last[0] if last else None;eid=str(uuid4());payload=snapshot.payload()
            if db.execute('SELECT 1 FROM descriptive_evidence WHERE evidence_id=?',(eid,)).fetchone(): raise ValueError('Duplicate evidence id.')
            try: db.execute('INSERT INTO descriptive_evidence(evidence_id,evidence_type,payload_json,created_at,evidence_family_id,evidence_version,previous_evidence_id,schema_version) VALUES(?,?,?,?,?,?,?,?)',(eid,snapshot.evidence_type,json.dumps(payload,ensure_ascii=False),snapshot.created_at.isoformat(),family_id,version,previous,EVIDENCE_SCHEMA_VERSION));db.commit()
            except sqlite3.IntegrityError as error: raise ValueError('Invalid evidence version history.') from error
        return VersionedEvidence(eid,family_id,version,previous,snapshot.created_at.isoformat(),EVIDENCE_SCHEMA_VERSION,payload)
    def get(self,evidence_id:str)->VersionedEvidence|None:
        with closing(sqlite3.connect(self.path)) as db:r=db.execute('SELECT evidence_id,evidence_family_id,evidence_version,previous_evidence_id,created_at,schema_version,payload_json FROM descriptive_evidence WHERE evidence_id=?',(evidence_id,)).fetchone()
        return VersionedEvidence(r[0],r[1],r[2],r[3],r[4],r[5],json.loads(r[6])) if r else None
    def history(self,family_id:str)->list[VersionedEvidence]:
        with closing(sqlite3.connect(self.path)) as db: ids=[r[0] for r in db.execute('SELECT evidence_id FROM descriptive_evidence WHERE evidence_family_id=? ORDER BY evidence_version ASC',(family_id,))]
        return [x for i in ids if (x:=self.get(i))]
    def latest(self,family_id:str)->VersionedEvidence|None:
        rows=self.history(family_id);return rows[-1] if rows else None
