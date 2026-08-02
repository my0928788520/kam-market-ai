"""空明 KAM｜Observation Database & Query V0.1 — read-only queries."""
from __future__ import annotations
import json, sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal
from ..analysis.observation import Observation, ObservationDirection
from ..models import Instrument

@dataclass(frozen=True, slots=True)
class ObservationQuery:
    market: str|None=None; instrument: Instrument|None=None; symbol: str|None=None; session: str|None=None
    direction: ObservationDirection|None=None; observation_type: str|None=None
    exchange_event_at_from: datetime|None=None; exchange_event_at_to: datetime|None=None
    order: Literal['ASC','DESC']='ASC'; limit: int|None=None
    def __post_init__(self) -> None:
        if self.order not in ('ASC','DESC'): raise ValueError('order must be ASC or DESC')
        if self.limit is not None and self.limit < 1: raise ValueError('limit must be positive')

class ObservationQueryStore:
    def __init__(self,path: str|Path)->None:self.path=Path(path)
    def query(self,q: ObservationQuery)->list[Observation]:
        clauses=['category = ?']; values: list[object]=['OBSERVATION_V0_1']
        filters={'market':q.market,'instrument':q.instrument.value if q.instrument else None,'symbol':q.symbol,'session':q.session,'direction':q.direction.value if q.direction else None,'observation_type':q.observation_type}
        for name,value in filters.items():
            if value is not None: clauses.append(f"json_extract(payload_json, '$.{name}') = ?"); values.append(value)
        if q.exchange_event_at_from: clauses.append("json_extract(payload_json, '$.exchange_event_at') >= ?"); values.append(q.exchange_event_at_from.isoformat())
        if q.exchange_event_at_to: clauses.append("json_extract(payload_json, '$.exchange_event_at') <= ?"); values.append(q.exchange_event_at_to.isoformat())
        sql="SELECT payload_json FROM observations WHERE "+' AND '.join(clauses)+" ORDER BY json_extract(payload_json, '$.exchange_event_at') "+q.order
        if q.limit: sql+=' LIMIT ?'; values.append(q.limit)
        with closing(sqlite3.connect(self.path)) as db:
            db.execute('PRAGMA query_only = ON')
            return [self._observation(json.loads(row[0])) for row in db.execute(sql,values)]
    @staticmethod
    def _observation(x: dict[str,object])->Observation:
        def dt(n:str)->datetime|None:
            v=x.get(n); return datetime.fromisoformat(v) if isinstance(v,str) else None
        return Observation(str(x['observation_id']),str(x['market']),Instrument(str(x['instrument'])),str(x['symbol']),dt('exchange_event_at'),dt('received_at'),str(x['session']),float(x['price']),int(x['volume']),ObservationDirection(str(x['direction'])),str(x['source']),str(x['observation_type']),dt('created_at'))
