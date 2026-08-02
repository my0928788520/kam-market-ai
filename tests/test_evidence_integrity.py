import sqlite3,tempfile,unittest
from dataclasses import replace
from datetime import UTC,datetime
from kam_market_ai.analysis.evidence import DescriptiveEvidenceCriteria,DescriptiveEvidenceEngine
from kam_market_ai.analysis.evidence_contracts import CriteriaCanonicalCodec,EVIDENCE_AGGREGATION_METHOD,EVIDENCE_SCHEMA_VERSION,EVIDENCE_TYPE
from kam_market_ai.analysis.evidence_versioning import EvidenceVersionStore,evidence_family_id
from kam_market_ai.analysis.observation import MappedMarketEvent,ObservationFactory
from kam_market_ai.analysis.traceability import EvidenceTraceabilityStore
from kam_market_ai.models import Instrument
from kam_market_ai.storage import ObservationQueryStore,ShadowStore

class Tests(unittest.TestCase):
 def test_official_append_boundary_and_immutable_chain(self):
  with tempfile.TemporaryDirectory() as d:
   s=ShadowStore(f'{d}/x.db');s.initialize();now=datetime.now(UTC);s.save_observation(ObservationFactory().from_mapped_event(MappedMarketEvent('TAIFEX',Instrument.TX,'TX',now,now,1,1,'trades')))
   e=DescriptiveEvidenceEngine(ObservationQueryStore(s.path)).summarize(DescriptiveEvidenceCriteria(market='TAIFEX',instrument=Instrument.TX,symbol='TX'))
   v=EvidenceVersionStore(s.path);a=v.append(e);b=v.append(replace(e,observation_count=2));c=v.append(replace(e,observation_count=3))
   self.assertEqual((a.evidence_version,b.evidence_version,c.evidence_version),(1,2,3));self.assertEqual((a.previous_evidence_id,b.previous_evidence_id,c.previous_evidence_id),(None,a.evidence_id,b.evidence_id));self.assertEqual(a.payload,v.get(a.evidence_id).payload)
   with self.assertRaises(TypeError): v.append(e, 'forged')
   db=sqlite3.connect(s.path)
   self.assertEqual(db.execute('SELECT COUNT(*) FROM descriptive_evidence').fetchone()[0],3)
   with self.assertRaises(sqlite3.IntegrityError): db.execute('INSERT INTO descriptive_evidence(evidence_id,evidence_type,payload_json,created_at,evidence_family_id,evidence_version) VALUES(?,?,?,?,?,?)',('duplicate',EVIDENCE_TYPE,'{}','x',a.evidence_family_id,1))
   db.close()
   self.assertIsNotNone(EvidenceTraceabilityStore(s.path).get(a.evidence_id))
 def test_codec_constants_and_central_schema(self):
  criteria=DescriptiveEvidenceCriteria(market=None,instrument=Instrument.TX,symbol='TX',exchange_event_at_from=datetime(2026,7,1,tzinfo=UTC))
  payload=CriteriaCanonicalCodec.canonical_payload(criteria);self.assertEqual(payload['market'],None);self.assertEqual(CriteriaCanonicalCodec.to_query(payload).symbol,'TX');self.assertEqual(CriteriaCanonicalCodec.canonical_json(payload),CriteriaCanonicalCodec.canonical_json(dict(reversed(list(payload.items())))))
  self.assertEqual(evidence_family_id(payload,EVIDENCE_TYPE),evidence_family_id(criteria.payload(),EVIDENCE_TYPE));self.assertEqual((EVIDENCE_AGGREGATION_METHOD,EVIDENCE_SCHEMA_VERSION,EVIDENCE_TYPE),('QUERY_AGGREGATION','DESCRIPTIVE_EVIDENCE_SCHEMA_V0_1','DESCRIPTIVE_OBSERVATION_SUMMARY_V0_1'))
  with tempfile.TemporaryDirectory() as d:
   s=ShadowStore(f'{d}/x.db');s.initialize()
   db=sqlite3.connect(s.path);self.assertIsNotNone(db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='evidence_change_timelines'").fetchone());db.close()
if __name__=='__main__':unittest.main()
