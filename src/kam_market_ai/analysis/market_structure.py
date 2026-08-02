"""Transparent, testable primitives for market structure analysis."""
from __future__ import annotations
from statistics import fmean, pstdev
from ..models import Candle, MarketRegime, PriceZone

def moving_average(candles: list[Candle], periods: int = 20) -> float | None:
    return None if len(candles) < periods else fmean(c.close for c in candles[-periods:])

def classify_regime(candles: list[Candle], lookback: int = 6, consolidation_ratio: float = .012) -> MarketRegime:
    if len(candles) < lookback: return MarketRegime.UNKNOWN
    recent=candles[-lookback:]; closes=[c.close for c in recent]; mean=fmean(closes)
    if not mean: return MarketRegime.UNKNOWN
    if pstdev(closes)/mean <= consolidation_ratio: return MarketRegime.CONSOLIDATION
    if closes[-1] > closes[0]: return MarketRegime.TREND_UP
    if closes[-1] < closes[0]: return MarketRegime.TREND_DOWN
    return MarketRegime.UNKNOWN

def dynamic_zones(candles: list[Candle], lookback: int = 20, width_ratio: float = .001) -> tuple[PriceZone, PriceZone] | None:
    if len(candles) < lookback: return None
    recent=candles[-lookback:]; support=min(c.low for c in recent); resistance=max(c.high for c in recent)
    return (PriceZone(support*(1-width_ratio),support*(1+width_ratio),"dynamic_support"),
            PriceZone(resistance*(1-width_ratio),resistance*(1+width_ratio),"dynamic_resistance"))

def v_reversal(candles: list[Candle], recovery_ratio: float = .7) -> bool:
    if len(candles) < 3: return False
    a,b,c=candles[-3:]; fall=a.close-b.low
    return fall > 0 and c.close >= b.low + fall*recovery_ratio and c.close > b.close

