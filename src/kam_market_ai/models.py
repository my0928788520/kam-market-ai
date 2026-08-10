"""Shared normalized domain models; no broker-order model exists."""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum


class Instrument(StrEnum): TAIEX="TAIEX"; TX="TX"; MTX="MTX"; TMF="TMF"
class SessionKind(StrEnum): DAY="DAY"; NIGHT="NIGHT"; CLOSED="CLOSED"
class MarketRegime(StrEnum):
    TREND_UP="TREND_UP"; TREND_DOWN="TREND_DOWN"; CONSOLIDATION="CONSOLIDATION"; UNKNOWN="UNKNOWN"
class DecisionState(StrEnum): WAIT="WAIT"; ELIGIBLE="ELIGIBLE"
class SignalGrade(StrEnum): NONE="NONE"; A="A"; A_PLUS="A+"
class Side(StrEnum): LONG="LONG"; SHORT="SHORT"

@dataclass(frozen=True, slots=True)
class Tick:
    instrument: Instrument; timestamp: datetime; price: float; volume: int = 0
    source_symbol: str | None = None
    source_channel: str | None = None
    after_hours: bool | None = None

@dataclass(frozen=True, slots=True)
class Candle:
    instrument: Instrument; start: datetime; end: datetime
    open: float; high: float; low: float; close: float; volume: int

@dataclass(frozen=True, slots=True)
class PriceZone:
    lower: float; upper: float; label: str
    def contains(self, price: float) -> bool: return self.lower <= price <= self.upper

@dataclass(frozen=True, slots=True)
class MarketContext:
    instrument: Instrument; timestamp: datetime; session: SessionKind; price: float
    opening_price: float | None = None; ma20: float | None = None
    regime: MarketRegime = MarketRegime.UNKNOWN
    support_zones: tuple[PriceZone, ...] = (); resistance_zones: tuple[PriceZone, ...] = ()
    taiex_background_available: bool = False; overseas_background_available: bool = False
    v_reversal_confirmed: bool = False; facts: Mapping[str, bool] = field(default_factory=dict)

@dataclass(frozen=True, slots=True)
class Decision:
    state: DecisionState; grade: SignalGrade; reasons: tuple[str, ...]; score: int = 0
    @property
    def message(self) -> str:
        return ("今日無符合條件訊號，但隨時可能出現訊號。" if self.state is DecisionState.WAIT
                else f"Shadow 候選訊號：{self.grade.value}")
