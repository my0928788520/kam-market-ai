import tempfile,unittest
from dataclasses import replace
from datetime import UTC,datetime
from kam_market_ai.analysis.evidence import DescriptiveEvidenceCriteria,DescriptiveEvidenceEngine
from kam_market_ai.analysis.evidence_comparison import EvidenceComparisonStore
from kam_market_ai.analysis.observation import MappedMarketEvent,ObservationFactory
from kam_market_ai.models import Instrument
from kam_market_ai.storage import ShadowStore,ObservationQueryStore
class Tests(unittest.TestCase):
 def test_versions_diff_validation_and_persistence(self):
  with tempfile.TemporaryDirectory() as d:
   s=ShadowStore(f'{d}/x.db');s.initialize();o=ObservationFactory().from_mapped_event(MappedMarketEvent('TAIFEX',Instrument.TX,'TX',datetime.now(UTC),datetime.now(UTC),1,1,'trades'));s.save_observation(o);e=DescriptiveEvidenceEngine(ObservationQueryStore(s.path)).summarize(DescriptiveEvidenceCriteria(symbol='TX'));v=EvidenceComparisonStore(s.path).versions;a=v.append(e);b=v.append(replace(e,observation_count=2));z=v.append(replace(e,observation_count=1));c=EvidenceComparisonStore(s.path);x=c.compare(a.evidence_id,b.evidence_id);y=c.compare(a.evidence_id,z.evidence_id);self.assertEqual((x.observation_count_delta,y.observation_count_delta),(1,0));self.assertIn('observation_count',x.payload_diff['changed']);c.save(x);self.assertEqual(c.get(x.comparison_id)['comparison_id'],x.comparison_id);self.assertRaises(ValueError,c.compare,b.evidence_id,a.evidence_id);self.assertRaises(ValueError,c.compare,a.evidence_id,a.evidence_id);self.assertRaises(LookupError,c.compare,'missing',a.evidence_id)
if __name__=='__main__':unittest.main()
