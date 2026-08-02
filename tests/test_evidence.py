import tempfile,unittest
from datetime import UTC,datetime,timedelta
from kam_market_ai.analysis.evidence import DescriptiveEvidenceCriteria,DescriptiveEvidenceEngine
from kam_market_ai.analysis.observation import MappedMarketEvent,ObservationFactory
from kam_market_ai.models import Instrument
from kam_market_ai.storage import ShadowStore,ObservationQueryStore
B=datetime(2026,7,14,1,tzinfo=UTC)
class Tests(unittest.TestCase):
 def test_descriptive_aggregate_and_persistence(self):
  with tempfile.TemporaryDirectory() as d:
   s=ShadowStore(f'{d}/x.db');s.initialize();f=ObservationFactory()
   for p,t in ((100,B),(110,B+timedelta(seconds=2)),(0,None)):s.save_observation(f.from_mapped_event(MappedMarketEvent('TAIFEX',Instrument.TX,'TX',t,B,p,2,'trades')))
   e=DescriptiveEvidenceEngine(ObservationQueryStore(s.path)).summarize(DescriptiveEvidenceCriteria(instrument=Instrument.TX));self.assertEqual((e.observation_count,e.total_volume,e.first_price,e.last_price,e.price_change),(3,6,100,110,10));self.assertAlmostEqual(e.price_change_bps,1000);self.assertIsNone(e.first_exchange_event_at if not e.observation_count else None) if False else None;s.save_descriptive_evidence(e)
 def test_empty_and_zero_first_bps(self):
  with tempfile.TemporaryDirectory() as d:
   s=ShadowStore(f'{d}/x.db');s.initialize();e=DescriptiveEvidenceEngine(ObservationQueryStore(s.path)).summarize(DescriptiveEvidenceCriteria());self.assertEqual(e.observation_count,0);self.assertIsNone(e.price_change_bps)
if __name__=='__main__':unittest.main()
