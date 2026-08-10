"""Fubon Neo market-data-only adapter.

This module deliberately does not import FubonSDK, CoreSDK, order classes, or
account objects. Login and authorization are outside KAM; this adapter receives
only the four already-authorized market-data clients it needs.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol

from kam_market_ai.market_data.base import MarketDataProvider
from kam_market_ai.models import Candle, Instrument, Tick

TAIEX_INDEX_SYMBOL = "IR0001"


class MarketDataBoundaryError(ValueError):
    """Raised when a non-market-data object reaches the adapter boundary."""


class ContractResolutionError(LookupError):
    """Raised when a verified futures contract mapping is not available."""


class HistoricalMappingRequiredError(RuntimeError):
    """Raised instead of guessing undocumented REST request/response fields."""


class FuturesWebSocket(Protocol):
    def on(self, event: str, listener: Callable[[str | Mapping[str, Any]], None]) -> Any: ...
    def off(self, event: str, listener: Callable[[str | Mapping[str, Any]], None]) -> Any: ...
    def connect(self) -> Any: ...
    def subscribe(self, params: Mapping[str, Any]) -> Any: ...
    def unsubscribe(self, params: Mapping[str, Any]) -> Any: ...
    def disconnect(self) -> Any: ...


class StockWebSocket(FuturesWebSocket, Protocol):
    pass


class FuturesRest(Protocol):
    @property
    def intraday(self) -> Any: ...

    @property
    def historical(self) -> Any: ...


class StockRest(Protocol):
    pass


def _reject_non_marketdata_client(value: object, field_name: str) -> None:
    """Reject composite SDK/account objects without importing their types."""
    forbidden = (
        "login",
        "apikey_login",
        "dma_login",
        "accounting",
        "futopt_accounting",
    )
    if any(hasattr(value, name) for name in forbidden):
        raise MarketDataBoundaryError(f"{field_name} must be a market-data client, not an SDK/account object")


def _require_marketdata_members(value: object, field_name: str, members: tuple[str, ...]) -> None:
    missing = tuple(name for name in members if not hasattr(value, name))
    if missing:
        raise MarketDataBoundaryError(f"{field_name} is missing market-data members: {', '.join(missing)}")


@dataclass(frozen=True, slots=True)
class AuthorizedMarketDataClients:
    """The only SDK-derived objects accepted by the KAM adapter."""

    futopt_websocket: FuturesWebSocket
    futopt_rest: FuturesRest
    stock_websocket: StockWebSocket
    stock_rest: StockRest

    def __post_init__(self) -> None:
        checks = {
            "futopt_websocket": ("on", "off", "connect", "subscribe", "unsubscribe", "disconnect"),
            "futopt_rest": ("intraday", "historical"),
            "stock_websocket": ("on", "off", "connect", "subscribe", "unsubscribe", "disconnect"),
            "stock_rest": ("intraday", "historical"),
        }
        for name, members in checks.items():
            value = getattr(self, name)
            if value is None:
                raise MarketDataBoundaryError(f"{name} is required")
            _reject_non_marketdata_client(value, name)
            _require_marketdata_members(value, name, members)


@dataclass(frozen=True, slots=True)
class ResolvedFuturesContract:
    instrument: Instrument
    symbol: str
    after_hours: bool


class InstrumentResolver(Protocol):
    def resolve(self, instrument: Instrument, *, after_hours: bool) -> ResolvedFuturesContract: ...


class VerifiedContractResolver:
    """Uses only externally verified, injected TX/MTX mappings; never guesses months."""

    def __init__(self, contracts: Sequence[ResolvedFuturesContract]) -> None:
        self._contracts = {(contract.instrument, contract.after_hours): contract for contract in contracts}

    def resolve(self, instrument: Instrument, *, after_hours: bool) -> ResolvedFuturesContract:
        try:
            return self._contracts[(instrument, after_hours)]
        except KeyError as error:
            raise ContractResolutionError(
                f"No verified contract mapping for {instrument.value}, after_hours={after_hours}"
            ) from error


class FubonFuturesDiscovery:
    """Thin, explicit port for the documented futopt.intraday.tickers endpoint.

    The caller supplies verified official query parameters. It intentionally does
    not turn returned contracts into TX/MTX mappings automatically.
    """

    def __init__(self, futopt_rest: FuturesRest) -> None:
        _reject_non_marketdata_client(futopt_rest, "futopt_rest")
        self._futopt_rest = futopt_rest

    def list_tickers(self, **official_params: object) -> Any:
        return self._futopt_rest.intraday.tickers(**official_params)


class HistoricalRequestMapper(Protocol):
    def build(
        self,
        contract: ResolvedFuturesContract,
        start: datetime,
        end: datetime,
        interval_minutes: int,
    ) -> Mapping[str, object]: ...


class HistoricalCandleDecoder(Protocol):
    def decode(self, instrument: Instrument, payload: object) -> list[Candle]: ...


class UnconfiguredHistoricalRequestMapper:
    def build(
        self,
        contract: ResolvedFuturesContract,
        start: datetime,
        end: datetime,
        interval_minutes: int,
    ) -> Mapping[str, object]:
        raise HistoricalMappingRequiredError(
            "Configure official REST candle parameters before requesting historical data"
        )


class UnconfiguredHistoricalCandleDecoder:
    def decode(self, instrument: Instrument, payload: object) -> list[Candle]:
        raise HistoricalMappingRequiredError(
            "Configure the official REST candle response decoder before using historical data"
        )


def _timestamp(value: object) -> datetime:
    if isinstance(value, datetime):
        return value.astimezone(UTC) if value.tzinfo else value.replace(tzinfo=UTC)
    if not isinstance(value, (int, float)):
        raise TypeError("market-data time must be a datetime or numeric epoch")
    numeric = float(value)
    if numeric > 100_000_000_000_000:
        numeric /= 1_000_000  # SDK examples use microseconds.
    elif numeric > 100_000_000_000:
        numeric /= 1_000  # Accept milliseconds for recorded fixtures.
    return datetime.fromtimestamp(numeric, tz=UTC)


class FubonNeoMarketDataAdapter(MarketDataProvider):
    """Converts authorized Fubon market-data callbacks to KAM Tick/Candle models."""

    def __init__(
        self,
        clients: AuthorizedMarketDataClients,
        resolver: InstrumentResolver,
        historical_request_mapper: HistoricalRequestMapper | None = None,
        historical_candle_decoder: HistoricalCandleDecoder | None = None,
    ) -> None:
        if not isinstance(clients, AuthorizedMarketDataClients):
            raise MarketDataBoundaryError("adapter accepts only AuthorizedMarketDataClients")
        self._clients = clients
        self._resolver = resolver
        self._request_mapper = historical_request_mapper or UnconfiguredHistoricalRequestMapper()
        self._candle_decoder = historical_candle_decoder or UnconfiguredHistoricalCandleDecoder()

    async def stream_ticks(
        self, instruments: tuple[Instrument, ...], *, after_hours: bool = False
    ) -> AsyncIterator[Tick]:
        """Subscribe only to documented trades/indices channels when iteration begins.

        `after_hours` is transport metadata only. KAM's SessionEngine remains the
        source of session classification and no trading hours are inferred here.
        """
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue[Tick] = asyncio.Queue()
        futures_symbols: dict[str, Instrument] = {}

        def enqueue(tick: Tick) -> None:
            loop.call_soon_threadsafe(queue.put_nowait, tick)

        def futures_message(message: str | Mapping[str, Any]) -> None:
            for tick in self._decode_futures_trades(message, futures_symbols, after_hours):
                enqueue(tick)

        def stock_message(message: str | Mapping[str, Any]) -> None:
            tick = self._decode_taiex_index(message)
            if tick is not None:
                enqueue(tick)

        wants_taiex = Instrument.TAIEX in instruments
        futures = tuple(instrument for instrument in instruments if instrument in {Instrument.TX, Instrument.MTX})
        self._clients.futopt_websocket.on("message", futures_message)
        if wants_taiex:
            self._clients.stock_websocket.on("message", stock_message)
        try:
            futures_subscriptions: list[dict[str, Any]] = []
            stock_subscription: dict[str, Any] | None = None
            if futures:
                self._clients.futopt_websocket.connect()
                for instrument in futures:
                    contract = self._resolver.resolve(instrument, after_hours=after_hours)
                    futures_symbols[contract.symbol] = instrument
                    params: dict[str, Any] = {"channel": "trades", "symbol": contract.symbol}
                    if after_hours:
                        params["afterHours"] = True
                    self._clients.futopt_websocket.subscribe(params)
                    futures_subscriptions.append(params)
            if wants_taiex:
                self._clients.stock_websocket.connect()
                stock_subscription = {"channel": "indices", "symbol": TAIEX_INDEX_SYMBOL}
                self._clients.stock_websocket.subscribe(stock_subscription)
            while True:
                yield await queue.get()
        finally:
            for params in locals().get("futures_subscriptions", []):
                self._clients.futopt_websocket.unsubscribe(params)
            if futures:
                self._clients.futopt_websocket.disconnect()
            if locals().get("stock_subscription") is not None:
                self._clients.stock_websocket.unsubscribe(stock_subscription)
            if wants_taiex:
                self._clients.stock_websocket.disconnect()
            self._clients.futopt_websocket.off("message", futures_message)
            if wants_taiex:
                self._clients.stock_websocket.off("message", stock_message)

    async def historical_candles(
        self,
        instrument: Instrument,
        start: datetime,
        end: datetime,
        interval_minutes: int,
    ) -> list[Candle]:
        del instrument, start, end, interval_minutes
        raise HistoricalMappingRequiredError(
            "Fubon officially documents futures candles as intraday-only; "
            "the futopt historical endpoint remains disabled"
        )

    @staticmethod
    def _as_message(message: str | Mapping[str, Any]) -> Mapping[str, Any] | None:
        parsed: object = json.loads(message) if isinstance(message, str) else message
        return parsed if isinstance(parsed, Mapping) else None

    @classmethod
    def _decode_futures_trades(
        cls,
        message: str | Mapping[str, Any],
        symbols: Mapping[str, Instrument],
        after_hours: bool,
    ) -> list[Tick]:
        event = cls._as_message(message)
        if event is None or event.get("event") != "data" or event.get("channel") != "trades":
            return []
        data = event.get("data")
        if not isinstance(data, Mapping):
            return []
        symbol = data.get("symbol")
        instrument = symbols.get(symbol) if isinstance(symbol, str) else None
        trades = data.get("trades")
        if instrument is None or not isinstance(trades, list) or "time" not in data:
            return []
        timestamp = _timestamp(data["time"])
        ticks: list[Tick] = []
        for trade in trades:
            if not isinstance(trade, Mapping) or not isinstance(trade.get("price"), (int, float)):
                continue
            size = trade.get("size", 0)
            ticks.append(
                Tick(
                    instrument=instrument,
                    timestamp=timestamp,
                    price=float(trade["price"]),
                    volume=int(size) if isinstance(size, (int, float)) else 0,
                    source_symbol=symbol,
                    source_channel="trades",
                    after_hours=after_hours,
                )
            )
        return ticks

    @classmethod
    def _decode_taiex_index(cls, message: str | Mapping[str, Any]) -> Tick | None:
        event = cls._as_message(message)
        if event is None or event.get("event") != "data" or event.get("channel") != "indices":
            return None
        data = event.get("data")
        if not isinstance(data, Mapping) or data.get("symbol") != TAIEX_INDEX_SYMBOL:
            return None
        index = data.get("index")
        if not isinstance(index, (int, float)) or "time" not in data:
            return None
        return Tick(
            instrument=Instrument.TAIEX,
            timestamp=_timestamp(data["time"]),
            price=float(index),
            source_symbol=TAIEX_INDEX_SYMBOL,
            source_channel="indices",
            after_hours=False,
        )
