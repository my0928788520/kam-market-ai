from __future__ import annotations
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from datetime import datetime
from ..models import Candle, Instrument, Tick

class MarketDataProvider(ABC):
    @abstractmethod
    async def stream_ticks(self, instruments: tuple[Instrument,...]) -> AsyncIterator[Tick]:
        if False: yield Tick(Instrument.MTX, datetime.now(), 0.0)
    @abstractmethod
    async def historical_candles(self, instrument: Instrument, start: datetime, end: datetime,
                                 interval_minutes: int) -> list[Candle]: raise NotImplementedError

