import tempfile,unittest
from datetime import UTC,datetime
from kam_market_ai.analysis.evidence import DescriptiveEvidenceCriteria,DescriptiveEvidenceEngine
from kam_market_ai.analysis.evidence_versioning import EvidenceVersionStore,evidence_family_id
from kam_market_ai.analysis.observation import MappedMarketEvent,ObservationFactory
from kam_market_ai.analysis.traceability import EvidenceTraceabilityStore,TraceabilityStatus
from kam_market_ai.models import Instrument
from kam_market_ai.storage import ShadowStore,ObservationQueryStore
class Tests(unittest.TestCase):
 def test_deterministic_identity_and_history(self):
  c={'market':'TAIFEX','instrument':'TX','symbol':'TX','session':'NIGHT','direction':None,'observation_type':'MARKET_TICK','exchange_event_at_from':None,'exchange_event_at_to':None};self.assertEqual(evidence_family_id(c,'X'),evidence_family_id(dict(reversed(list(c.items()))),'X'));self.assertNotEqual(evidence_family_id(c,'X'),evidence_family_id({**c,'symbol':'TMF'},'X'))
  with tempfile.TemporaryDirectory() as d:
   s=ShadowStore(f'{d}/x.db');s.initialize();o=ObservationFactory().from_mapped_event(MappedMarketEvent('TAIFEX',Instrument.TX,'TX',datetime.now(UTC),datetime.now(UTC),1,1,'trades'));s.save_observation(o);e=DescriptiveEvidenceEngine(ObservationQueryStore(s.path)).summarize(DescriptiveEvidenceCriteria(symbol='TX'));v=EvidenceVersionStore(s.path);a=v.append(e);b=v.append(e);z=v.append(e);self.assertEqual([x.evidence_version for x in v.history(a.evidence_family_id)],[1,2,3]);self.assertEqual((a.previous_evidence_id,b.previous_evidence_id,z.previous_evidence_id),(None,a.evidence_id,b.evidence_id));self.assertEqual(v.latest(a.evidence_family_id).evidence_id,z.evidence_id);self.assertIsNone(v.latest('missing'));self.assertEqual(a.payload,v.get(a.evidence_id).payload)
if __name__=='__main__':unittest.main()
