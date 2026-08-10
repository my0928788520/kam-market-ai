"""One-shot, market-data-only validation for documented Fubon candles."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from kam_market_ai.models import Instrument

from .fubon_neo import (
    AuthorizedMarketDataClients,
    FubonIntradayCandlesAdapter,
    OfficialIntradayCandleSpec,
    ResolvedFuturesContract,
    VerifiedContractResolver,
)


@dataclass(frozen=True, slots=True)
class FubonIntradayCandleProbeReport:
    instrument: Instrument
    symbol: str
    session: str
    timeframe: str
    interval_minutes: int
    candle_count: int
    first_candle_at: datetime | None
    last_candle_at: datetime | None
    endpoint_invoked: bool = True
    market_data_only: bool = True
    account_connected: bool = False
    broker_connected: bool = False
    trading_enabled: bool = False
    live_order_allowed: bool = False

    def safe_payload(self) -> dict[str, object]:
        return {
            "success": True,
            "mode": "one_shot_read_only_intraday_candles",
            "instrument": self.instrument.value,
            "symbol": self.symbol,
            "session": self.session,
            "timeframe": self.timeframe,
            "interval_minutes": self.interval_minutes,
            "candle_count": self.candle_count,
            "first_candle_at": self.first_candle_at.isoformat() if self.first_candle_at else None,
            "last_candle_at": self.last_candle_at.isoformat() if self.last_candle_at else None,
            "endpoint_invoked": self.endpoint_invoked,
            "market_data_only": self.market_data_only,
            "account_connected": self.account_connected,
            "broker_connected": self.broker_connected,
            "trading_enabled": self.trading_enabled,
            "live_order_allowed": self.live_order_allowed,
            "raw_payload_retained": False,
        }


class FubonIntradayCandleProbe:
    """Invoke exactly one documented candle request with caller-verified tokens."""

    def __init__(self, clients: AuthorizedMarketDataClients) -> None:
        if not isinstance(clients, AuthorizedMarketDataClients):
            raise TypeError("AuthorizedMarketDataClients is required")
        self._clients = clients

    def run(
        self,
        *,
        instrument: Instrument,
        symbol: str,
        session: str,
        timeframe: str,
        interval_minutes: int,
        after_hours: bool = False,
    ) -> FubonIntradayCandleProbeReport:
        if instrument not in {Instrument.TX, Instrument.MTX}:
            raise ValueError("intraday candle probe supports TX or MTX only")
        if not symbol or symbol.strip() != symbol:
            raise ValueError("a verified provider symbol is required")
        contract = ResolvedFuturesContract(instrument, symbol, after_hours)
        adapter = FubonIntradayCandlesAdapter(
            self._clients,
            VerifiedContractResolver((contract,)),
        )
        spec = OfficialIntradayCandleSpec(session, timeframe, interval_minutes)
        candles = adapter.fetch(instrument, spec, after_hours=after_hours)
        return FubonIntradayCandleProbeReport(
            instrument=instrument,
            symbol=symbol,
            session=session,
            timeframe=timeframe,
            interval_minutes=interval_minutes,
            candle_count=len(candles),
            first_candle_at=candles[0].start if candles else None,
            last_candle_at=candles[-1].start if candles else None,
        )
