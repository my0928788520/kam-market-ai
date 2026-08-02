import json, unittest
from kam_market_ai.market_data.lifecycle_probe import LifecycleFailureStage, WebSocketLifecycleProbe
from fugle_marketdata.websocket.client import AuthenticationState
from kam_market_ai.models import SessionKind
class Fake:
 def __init__(self, market=True): self.handlers={}; self.auth_status=AuthenticationState.PENDING; self.market=market; self.unsub=0; self.disc=0
 def on(self,e,l): self.handlers.setdefault(e,[]).append(l)
 def off(self,e,l): self.handlers[e].remove(l)
 def emit(self,e,v=None): [h(v) if v is not None else h() for h in tuple(self.handlers.get(e,[]))]
 def connect(self): self.emit("connect"); self.auth_status=AuthenticationState.AUTHENTICATED; self.emit("authenticated",{} )
 def subscribe(self,p):
  if self.market: self.emit("message",json.dumps({"event":"data","data":p}))
 def unsubscribe(self,p): self.unsub+=1
 def disconnect(self): self.disc+=1; self.emit("disconnect")
class Tests(unittest.TestCase):
 def test_lifecycle(self):
  f=Fake(); s=WebSocketLifecycleProbe().run(f,(WebSocketLifecycleProbe.stock_subscription(),),duration_seconds=.001)
  self.assertIs(s.failure_stage,LifecycleFailureStage.NONE); self.assertTrue(s.market_event_received); self.assertEqual((f.unsub,f.disc),(1,1))
 def test_futures_data_counts_by_symbol_only(self):
  f=Fake(); p=WebSocketLifecycleProbe(); s=p.run(f,(p.futures_subscription("TX"),p.futures_subscription("TMF")),duration_seconds=.001)
  self.assertEqual((s.tx_event_count,s.tmf_event_count),(1,1))
 def test_counter_three_tx_five_tmf_ignores_lifecycle_and_unknown_symbols(self):
  class Burst(Fake):
   def subscribe(self,p):
    for _ in range(3 if p["symbol"]=="TX" else 5): self.emit("message",json.dumps({"event":"data","data":{"symbol":p["symbol"],"afterHours":True}}))
    for name in ("connect","authenticated","subscribed","pong","heartbeat","disconnect"):
     self.emit("message",json.dumps({"event":name,"data":{"symbol":p["symbol"]}}))
    self.emit("message",json.dumps({"event":"data","data":{"symbol":"OTHER"}}))
  p=WebSocketLifecycleProbe(); s=p.run(Burst(),(p.futures_subscription("TX",after_hours=True),p.futures_subscription("TMF",after_hours=True)),duration_seconds=.001)
  self.assertEqual((s.tx_event_count,s.tmf_event_count),(3,5))
 def test_counter_resets_and_cleanup_preserves_completed_counts(self):
  p=WebSocketLifecycleProbe(); first=p.run(Fake(),(p.futures_subscription("TX"),p.futures_subscription("TMF")),duration_seconds=.001)
  second=p.run(Fake(False),(p.futures_subscription("TX"),p.futures_subscription("TMF")),duration_seconds=.001)
  self.assertEqual((first.tx_event_count,first.tmf_event_count),(1,1)); self.assertEqual((second.tx_event_count,second.tmf_event_count),(0,0))
 def test_no_market(self):
  s=WebSocketLifecycleProbe().run(Fake(False),(WebSocketLifecycleProbe.stock_subscription(),),duration_seconds=.001)
  self.assertIs(s.failure_stage,LifecycleFailureStage.NO_MARKET_EVENT)
 def test_session_aware_payloads_and_closed_refusal(self):
  p=WebSocketLifecycleProbe
  self.assertNotIn("afterHours",p.session_aware_futures_subscription("TX",SessionKind.DAY))
  self.assertTrue(p.session_aware_futures_subscription("TX",SessionKind.NIGHT)["afterHours"])
  with self.assertRaises(ValueError): p.session_aware_futures_subscription("TX",SessionKind.CLOSED)
if __name__=="__main__": unittest.main()
