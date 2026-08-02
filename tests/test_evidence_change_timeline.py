import tempfile,unittest
from dataclasses import replace
from datetime import UTC,datetime
from kam_market_ai.analysis.evidence import DescriptiveEvidenceCriteria,DescriptiveEvidenceEngine
from kam_market_ai.analysis.evidence_comparison import EvidenceComparisonStore
from kam_market_ai.analysis.evidence_timeline import EvidenceTimelineStore
from kam_market_ai.analysis.observation import MappedMarketEvent,ObservationFactory
from kam_market_ai.models import Instrument
from kam_market_ai.storage import ShadowStore,ObservationQueryStore
class Tests(unittest.TestCase):
 def test_single_adjacent_reuse_persistence_and_isolation(self):
  with tempfile.TemporaryDirectory() as d:
   s=ShadowStore(f'{d}/x.db');s.initialize();o=ObservationFactory().from_mapped_event(MappedMarketEvent('TAIFEX',Instrument.TX,'TX',datetime.now(UTC),datetime.now(UTC),1,1,'trades'));s.save_observation(o);e=DescriptiveEvidenceEngine(ObservationQueryStore(s.path)).summarize(DescriptiveEvidenceCriteria(symbol='TX'));v=EvidenceComparisonStore(s.path).versions;a=v.append(e);t=EvidenceTimelineStore(s.path);one=t.build(a.evidence_family_id);self.assertEqual((one.version_count,one.summary['observation_count_total_delta'],one.timeline_entries[0].comparison_from_previous),(1,0,None));b=v.append(replace(e,observation_count=2));z=v.append(replace(e,observation_count=3));two=t.build(a.evidence_family_id);self.assertEqual([x.evidence_version for x in two.timeline_entries],[1,2,3]);self.assertEqual(two.timeline_entries[2].comparison_from_previous['base_evidence_id'],b.evidence_id);count_before=len(EvidenceComparisonStore(s.path).find(a.evidence_id,b.evidence_id) or {});again=t.build(a.evidence_family_id);self.assertEqual(two.timeline_entries[1].comparison_from_previous['comparison_id'],again.timeline_entries[1].comparison_from_previous['comparison_id']);t.save(two);self.assertEqual(t.get(two.timeline_id)['timeline_id'],two.timeline_id);self.assertRaises(LookupError,t.build,'missing')
if __name__=='__main__':unittest.main()
