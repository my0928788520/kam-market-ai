"""空明 KAM｜Descriptive Evidence Engine V0.1 — aggregation only."""
from __future__ import annotations
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from uuid import uuid4
from ..models import Instrument
from ..analysis.observation import ObservationDirection
from ..storage.observation_query import ObservationQuery, ObservationQueryStore
from .evidence_contracts import CriteriaCanonicalCodec, EVIDENCE_TYPE

@dataclass(frozen=True, slots=True)
class DescriptiveEvidenceCriteria:
    market: str|None=None; instrument: Instrument|None=None; symbol: str|None=None; session: str|None=None; direction: ObservationDirection|None=None; observation_type: str|None=None; exchange_event_at_from: datetime|None=None; exchange_event_at_to: datetime|None=None
    def to_query(self)->ObservationQuery:return ObservationQuery(self.market,self.instrument,self.symbol,self.session,self.direction,self.observation_type,self.exchange_event_at_from,self.exchange_event_at_to,'ASC')
    def payload(self)->dict[str,object]:
        return CriteriaCanonicalCodec.canonical_payload(self)
@dataclass(frozen=True,slots=True)
class DescriptiveEvidenceSnapshot:
    evidence_id:str;evidence_type:str;criteria:dict[str,object];observation_count:int;first_exchange_event_at:datetime|None;last_exchange_event_at:datetime|None;direction_count:dict[str,int];up_count:int;down_count:int;flat_count:int;unknown_count:int;total_volume:int;min_price:float|None;max_price:float|None;first_price:float|None;last_price:float|None;price_change:float|None;price_change_bps:float|None;created_at:datetime
    def payload(self)->dict[str,object]:
        data=asdict(self)
        for name in ('first_exchange_event_at','last_exchange_event_at','created_at'):data[name]=getattr(self,name).isoformat() if getattr(self,name) else None
        return data
class DescriptiveEvidenceEngine:
    def __init__(self,queries:ObservationQueryStore)->None:self._queries=queries
    def summarize(self,criteria:DescriptiveEvidenceCriteria)->DescriptiveEvidenceSnapshot:
        rows=self._queries.query(criteria.to_query()); timed=sorted((r for r in rows if r.exchange_event_at is not None),key=lambda r:r.exchange_event_at)
        counts={x:sum(r.direction.value==x for r in rows) for x in ('UP','DOWN','FLAT','UNKNOWN')}; first=timed[0] if timed else None;last=timed[-1] if timed else None;change=last.price-first.price if first and last else None;b=None if not first or first.price==0 or change is None else change/first.price*10000;prices=[r.price for r in rows]
        return DescriptiveEvidenceSnapshot(str(uuid4()),EVIDENCE_TYPE,criteria.payload(),len(rows),first.exchange_event_at if first else None,last.exchange_event_at if last else None,counts,counts['UP'],counts['DOWN'],counts['FLAT'],counts['UNKNOWN'],sum(r.volume for r in rows),min(prices) if prices else None,max(prices) if prices else None,first.price if first else None,last.price if last else None,change,b,datetime.now(UTC))
