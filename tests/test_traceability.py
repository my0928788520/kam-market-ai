import gc,hashlib,json,sqlite3,tempfile,unittest
from datetime import UTC,datetime,timedelta
from kam_market_ai.analysis.evidence import DescriptiveEvidenceCriteria,DescriptiveEvidenceEngine
from kam_market_ai.analysis.observation import MappedMarketEvent,ObservationFactory,ObservationDirection
from kam_market_ai.analysis.traceability import EvidenceTraceabilityStore,TraceabilityStatus
from kam_market_ai.models import Instrument
from kam_market_ai.storage import ShadowStore,ObservationQueryStore
class Tests(unittest.TestCase):
 def test_complete_and_mismatch(self):
  with tempfile.TemporaryDirectory() as d:
   s=ShadowStore(f'{d}/x.db');s.initialize();o=ObservationFactory().from_mapped_event(MappedMarketEvent('TAIFEX',Instrument.TX,'TX',datetime.now(UTC),datetime.now(UTC),1,1,'trades'));s.save_observation(o);e=DescriptiveEvidenceEngine(ObservationQueryStore(s.path)).summarize(DescriptiveEvidenceCriteria(symbol='TX'));saved=s.save_descriptive_evidence(e);t=EvidenceTraceabilityStore(s.path);self.assertIs(t.get(saved.evidence_id).status,TraceabilityStatus.COMPLETE)
 def test_status_matrix_preservation_and_read_only(self):
  with tempfile.TemporaryDirectory() as d:
   s=ShadowStore(f'{d}/x.db');s.initialize();f=ObservationFactory();base=datetime(2026,7,14,1,tzinfo=UTC)
   for price,time in ((10,base),(11,base+timedelta(seconds=1))):s.save_observation(f.from_mapped_event(MappedMarketEvent('TAIFEX',Instrument.TX,'TX',time,time,price,1,'trades')))
   c=DescriptiveEvidenceCriteria(market='TAIFEX',instrument=Instrument.TX,symbol='TX',session='DAY',direction=ObservationDirection.UP,observation_type='MARKET_TICK',exchange_event_at_from=base,exchange_event_at_to=base+timedelta(seconds=2));e=DescriptiveEvidenceEngine(ObservationQueryStore(s.path)).summarize(c);saved=s.save_descriptive_evidence(e);t=EvidenceTraceabilityStore(s.path)
   with sqlite3.connect(s.path) as db: before=db.execute("SELECT payload_json FROM observations").fetchall(); ep=db.execute("SELECT payload_json FROM descriptive_evidence WHERE evidence_id=?",(saved.evidence_id,)).fetchone()[0]
   complete=t.get(saved.evidence_id);self.assertEqual(complete.source_query,c.payload());self.assertEqual(complete.status,TraceabilityStatus.COMPLETE);self.assertEqual((complete.observation_time_start,complete.observation_time_end),(e.first_exchange_event_at.isoformat(),e.last_exchange_event_at.isoformat()))
   with sqlite3.connect(s.path) as db:
    p=json.loads(ep);p['observation_count']=99;db.execute('UPDATE descriptive_evidence SET payload_json=? WHERE evidence_id=?',(json.dumps(p),saved.evidence_id));db.commit()
   self.assertIs(t.get(saved.evidence_id).status,TraceabilityStatus.COUNT_MISMATCH)
   with sqlite3.connect(s.path) as db:
    p['criteria']['symbol']='MISSING';p['observation_count']=1;db.execute('UPDATE descriptive_evidence SET payload_json=? WHERE evidence_id=?',(json.dumps(p),saved.evidence_id));db.commit()
   self.assertIs(t.get(saved.evidence_id).status,TraceabilityStatus.SOURCE_OBSERVATION_MISSING)
   with sqlite3.connect(s.path) as db:
    p['criteria']['instrument']='BAD';db.execute('UPDATE descriptive_evidence SET payload_json=? WHERE evidence_id=?',(json.dumps(p),saved.evidence_id));db.commit()
   self.assertIs(t.get(saved.evidence_id).status,TraceabilityStatus.QUERY_INVALID);self.assertIn(TraceabilityStatus.UNKNOWN,list(TraceabilityStatus))
   with sqlite3.connect(s.path) as db:self.assertEqual(before,db.execute("SELECT payload_json FROM observations").fetchall())
   del db;gc.collect()
if __name__=='__main__':unittest.main()
