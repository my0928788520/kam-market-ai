import tempfile, unittest
from datetime import UTC, datetime, timedelta
from kam_market_ai.analysis.observation import MappedMarketEvent, ObservationDirection, ObservationFactory
from kam_market_ai.config import RESEARCH_MODE, TRADING_ENABLED
from kam_market_ai.models import Instrument
from kam_market_ai.storage import ShadowStore

BASE=datetime(2026,7,14,1,tzinfo=UTC)
def event(symbol="TX", price=100, exchange=BASE, received=BASE+timedelta(milliseconds=5), instrument=Instrument.TX):
 return MappedMarketEvent("TAIFEX",instrument,symbol,exchange,received,price,2,"trades",False)
class ObservationTests(unittest.TestCase):
 def test_directions_and_timestamp_separation(self):
  f=ObservationFactory(); a=f.from_mapped_event(event(price=100)); b=f.from_mapped_event(event(price=101)); c=f.from_mapped_event(event(price=99)); d=f.from_mapped_event(event(price=99))
  self.assertEqual([x.direction for x in (a,b,c,d)],[ObservationDirection.UNKNOWN,ObservationDirection.UP,ObservationDirection.DOWN,ObservationDirection.FLAT]); self.assertNotEqual(a.exchange_event_at,a.received_at)
 def test_missing_exchange_and_symbols(self):
  f=ObservationFactory(); x=f.from_mapped_event(event(exchange=None)); y=f.from_mapped_event(event(symbol="TMF",instrument=Instrument.MTX));
  self.assertEqual(x.session,"UNKNOWN"); self.assertIsNone(x.exchange_event_at); self.assertEqual((y.instrument,y.symbol),(Instrument.MTX,"TMF"))
 def test_lifecycle_mapper_failure_and_persistence(self):
  f=ObservationFactory(); self.assertIsNone(f.from_lifecycle_event("connected")); self.assertIsNone(f.from_mapped_event(None)); o=f.from_mapped_event(event())
  with tempfile.TemporaryDirectory() as d:
   s=ShadowStore(f"{d}/o.db"); s.initialize(); s.save_observation(o); self.assertTrue(s.path.exists())
  self.assertTrue(RESEARCH_MODE); self.assertFalse(TRADING_ENABLED)
if __name__=='__main__': unittest.main()
