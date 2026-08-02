"""Deterministic time-bucket candle builder for feeds and replay."""
from __future__ import annotations
from datetime import timedelta
from .models import Candle, Tick

class CandleBuilder:
    def __init__(self, interval_minutes: int = 60) -> None:
        if interval_minutes <= 0: raise ValueError("interval_minutes must be positive")
        self.interval = interval_minutes; self._current: Candle | None = None
    def _start(self, tick: Tick):
        minute = (tick.timestamp.minute // self.interval) * self.interval
        return tick.timestamp.replace(minute=0, second=0, microsecond=0) + timedelta(minutes=minute)
    def add(self, tick: Tick) -> Candle | None:
        start = self._start(tick); end = start + timedelta(minutes=self.interval)
        if self._current is None:
            self._current = Candle(tick.instrument,start,end,tick.price,tick.price,tick.price,tick.price,tick.volume); return None
        if tick.instrument != self._current.instrument or start >= self._current.end:
            completed = self._current
            self._current = Candle(tick.instrument,start,end,tick.price,tick.price,tick.price,tick.price,tick.volume)
            return completed
        c=self._current
        self._current=Candle(c.instrument,c.start,c.end,c.open,max(c.high,tick.price),min(c.low,tick.price),tick.price,c.volume+tick.volume)
        return None
    def flush(self) -> Candle | None:
        current=self._current; self._current=None; return current

