import tempfile,unittest
from datetime import UTC,datetime,timedelta
from kam_market_ai.analysis.observation import MappedMarketEvent,ObservationFactory,ObservationDirection
from kam_market_ai.models import Instrument
from kam_market_ai.storage import ShadowStore,ObservationQuery,ObservationQueryStore
B=datetime(2026,7,14,1,tzinfo=UTC)
class Tests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.s=ShadowStore(f'{self.tmp.name}/q.db');self.s.initialize();f=ObservationFactory()
  self.rows=[f.from_mapped_event(MappedMarketEvent('TAIFEX',Instrument.TX,'TX',B,B,100,1,'trades')),f.from_mapped_event(MappedMarketEvent('TAIFEX',Instrument.TX,'TX',B+timedelta(seconds=1),B,101,2,'trades')),f.from_mapped_event(MappedMarketEvent('TAIFEX',Instrument.MTX,'TMF',B+timedelta(seconds=2),B,100,3,'trades')),f.from_mapped_event(MappedMarketEvent('TAIFEX',Instrument.MTX,'TMF',None,B,100,4,'trades'))]
  for r in self.rows:self.s.save_observation(r)
  self.q=ObservationQueryStore(self.s.path)
 def tearDown(self):self.tmp.cleanup()
 def test_filters_reconstruction_and_isolation(self):
  x=self.q.query(ObservationQuery(market='TAIFEX',instrument=Instrument.TX,symbol='TX',direction=ObservationDirection.UP));self.assertEqual(len(x),1);self.assertIsInstance(x[0],type(self.rows[0]));self.assertEqual(len(self.q.query(ObservationQuery(session='UNKNOWN'))),1);self.assertEqual(len(self.q.query(ObservationQuery(observation_type='MARKET_TICK'))),4);self.assertEqual(len(self.q.query(ObservationQuery(symbol='NONE'))),0)
 def test_range_order_limit_missing_and_no_mutation(self):
  asc=self.q.query(ObservationQuery(exchange_event_at_from=B,order='ASC'));desc=self.q.query(ObservationQuery(exchange_event_at_from=B,order='DESC',limit=1));self.assertEqual((asc[0].symbol,desc[0].symbol),('TX','TMF'));self.assertIsNone(self.q.query(ObservationQuery(session='UNKNOWN'))[0].exchange_event_at);self.assertEqual(self.rows[0].price,100)
if __name__=='__main__':unittest.main()
