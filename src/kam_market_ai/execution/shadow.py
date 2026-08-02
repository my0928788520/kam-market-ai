"""In-memory Shadow execution only; cannot communicate with a broker."""
from __future__ import annotations
from dataclasses import dataclass, replace
from datetime import datetime
from uuid import uuid4
from ..config import TRADING_ENABLED, UnsafeConfigurationError
from ..models import Decision, DecisionState, Instrument, Side

@dataclass(frozen=True, slots=True)
class ShadowTrade:
    id: str; instrument: Instrument; side: Side; quantity: int; entry_time: datetime; entry_price: float
    stop_price: float; target_price: float; invalidation: str
    mfe: float=0.0; mae: float=0.0; exit_time: datetime | None=None; exit_price: float | None=None; exit_reason: str | None=None

class ShadowExecutor:
    def __init__(self) -> None:
        if TRADING_ENABLED: raise UnsafeConfigurationError("Shadow executor refused unsafe configuration")
    def enter(self, decision: Decision, instrument: Instrument, side: Side, price: float,
              timestamp: datetime, stop_price: float, target_price: float, invalidation: str,
              quantity: int=1) -> ShadowTrade:
        if decision.state is not DecisionState.ELIGIBLE: raise ValueError("WAIT decisions cannot enter")
        if instrument is not Instrument.MTX or quantity != 1: raise ValueError("V0.1 permits exactly one MTX Shadow unit")
        if not invalidation.strip(): raise ValueError("invalidation condition is required")
        if side is Side.LONG and not stop_price < price < target_price: raise ValueError("invalid LONG exits")
        if side is Side.SHORT and not target_price < price < stop_price: raise ValueError("invalid SHORT exits")
        return ShadowTrade(uuid4().hex,instrument,side,quantity,timestamp,price,stop_price,target_price,invalidation)
    def mark(self, trade: ShadowTrade, price: float, timestamp: datetime, cause_valid: bool=True) -> ShadowTrade:
        favorable=(price-trade.entry_price) if trade.side is Side.LONG else (trade.entry_price-price)
        updated=replace(trade,mfe=max(trade.mfe,favorable),mae=max(trade.mae,-favorable))
        stop_hit=price <= trade.stop_price if trade.side is Side.LONG else price >= trade.stop_price
        target_hit=price >= trade.target_price if trade.side is Side.LONG else price <= trade.target_price
        reason="STOP" if stop_hit else "TARGET" if target_hit else "CAUSE_INVALID" if not cause_valid else None
        return replace(updated,exit_time=timestamp,exit_price=price,exit_reason=reason) if reason else updated

