"""Persistent, read-only Fubon futures quotes for the local KAM dashboard.

The client accepts only the already-authorized market-data boundary plus the
contracts verified by Sprint 9A.  It never receives an SDK, login result,
account, position, balance, or order object.
"""

from __future__ import annotations

import json
import threading
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from time import monotonic
from typing import Any

from kam_market_ai.live_read_only.live_market_adapter import (
    LiveMarketDataError,
    LiveMarketDataRecord,
    LiveMarketReadStatus,
)
from kam_market_ai.live_read_only.market_snapshot import TradingSession
from kam_market_ai.market_data.fubon_neo import AuthorizedMarketDataClients
from kam_market_ai.market_data.futures_live_probe import (
    FubonLiveFuturesContract,
    FuturesProductCode,
)

_PRODUCT_NAMES = {
    FuturesProductCode.TX: "臺股期貨",
    FuturesProductCode.MTX: "小型臺指期貨",
    FuturesProductCode.TMF: "微型臺指期貨",
}


class FubonFuturesRuntimeStatus(StrEnum):
    IDLE = "IDLE"
    STARTING = "STARTING"
    READY = "READY"
    DEGRADED = "DEGRADED"
    CLOSED = "CLOSED"


class FubonFuturesRuntimeFailure(StrEnum):
    CONNECT_ERROR = "CONNECT_ERROR"
    CONNECT_TIMEOUT = "CONNECT_TIMEOUT"
    AUTH_TIMEOUT = "AUTH_TIMEOUT"
    SUBSCRIBE_ERROR = "SUBSCRIBE_ERROR"
    SUBSCRIBE_ACK_TIMEOUT = "SUBSCRIBE_ACK_TIMEOUT"
    NO_FRESH_DATA = "NO_FRESH_DATA"
    PROVIDER_PAYLOAD_ERROR = "PROVIDER_PAYLOAD_ERROR"


class FubonFuturesRuntimeError(RuntimeError):
    """Stable startup failure that never includes a provider payload."""

    def __init__(self, stage: FubonFuturesRuntimeFailure) -> None:
        self.stage = stage
        super().__init__(stage.value)


@dataclass(frozen=True, slots=True)
class FubonFuturesRuntimeConfig:
    connect_timeout_seconds: float = 10.0
    subscribe_timeout_seconds: float = 10.0
    initial_data_timeout_seconds: float = 30.0
    cleanup_timeout_seconds: float = 5.0

    def __post_init__(self) -> None:
        if (
            min(
                self.connect_timeout_seconds,
                self.subscribe_timeout_seconds,
                self.initial_data_timeout_seconds,
                self.cleanup_timeout_seconds,
            )
            <= 0
        ):
            raise ValueError("Fubon runtime timeouts must be positive.")


_DEFAULT_RUNTIME_CONFIG = FubonFuturesRuntimeConfig()


@dataclass(frozen=True, slots=True)
class _CachedQuote:
    source_timestamp: datetime
    last_price: Decimal
    volume: Decimal


def _provider_timestamp(value: object) -> datetime:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise TypeError("invalid provider timestamp")
    numeric = float(value)
    if numeric > 100_000_000_000_000:
        numeric /= 1_000_000
    elif numeric > 100_000_000_000:
        numeric /= 1_000
    return datetime.fromtimestamp(numeric, tz=UTC)


class FubonFuturesLiveClient:
    """Keep verified TX/MTX/TMF trade subscriptions available to MarketSnapshot."""

    def __init__(
        self,
        clients: AuthorizedMarketDataClients,
        contracts: tuple[FubonLiveFuturesContract, ...],
        config: FubonFuturesRuntimeConfig = _DEFAULT_RUNTIME_CONFIG,
        *,
        clock: Callable[[], datetime] = lambda: datetime.now(tz=UTC),
    ) -> None:
        if not isinstance(clients, AuthorizedMarketDataClients):
            raise TypeError("AuthorizedMarketDataClients is required")
        if tuple(item.product_code for item in contracts) != tuple(FuturesProductCode):
            raise ValueError("TX, MTX, and TMF contracts are required in canonical order")
        if len({item.after_hours for item in contracts}) != 1:
            raise ValueError("All runtime contracts must use the same trading session")
        self._websocket = clients.futopt_websocket
        self._contracts = contracts
        self._by_symbol = {item.provider_symbol: item for item in contracts}
        self._config = config
        self._clock = clock
        self._status = FubonFuturesRuntimeStatus.IDLE
        self._connected = False
        self._authenticated = False
        self._provider_error = False
        self._closing = False
        self._subscription_ids: dict[str, str] = {}
        self._unsubscribed_ids: set[str] = set()
        self._quotes: dict[str, _CachedQuote] = {}
        self._lock = threading.Lock()
        self._changed = threading.Event()
        self._listeners = self._build_listeners()

    @property
    def status(self) -> FubonFuturesRuntimeStatus:
        with self._lock:
            return self._status

    @property
    def connection_ready(self) -> bool:
        return self.status is FubonFuturesRuntimeStatus.READY

    def start(self) -> None:
        with self._lock:
            if self._status is not FubonFuturesRuntimeStatus.IDLE:
                raise FubonFuturesRuntimeError(FubonFuturesRuntimeFailure.CONNECT_ERROR)
            self._status = FubonFuturesRuntimeStatus.STARTING
        try:
            for event, listener in self._listeners:
                self._websocket.on(event, listener)
            try:
                self._websocket.connect()
            except Exception:  # noqa: BLE001 -- provider SDK exception types are not stable
                raise FubonFuturesRuntimeError(FubonFuturesRuntimeFailure.CONNECT_ERROR) from None
            if not self._wait(
                lambda: self._connected or self._provider_error,
                self._config.connect_timeout_seconds,
            ):
                raise FubonFuturesRuntimeError(FubonFuturesRuntimeFailure.CONNECT_TIMEOUT)
            if self._provider_error:
                raise FubonFuturesRuntimeError(FubonFuturesRuntimeFailure.CONNECT_ERROR)
            if not self._wait(
                lambda: self._authenticated or self._provider_error,
                self._config.connect_timeout_seconds,
            ):
                raise FubonFuturesRuntimeError(FubonFuturesRuntimeFailure.AUTH_TIMEOUT)
            if self._provider_error:
                raise FubonFuturesRuntimeError(FubonFuturesRuntimeFailure.AUTH_TIMEOUT)
            for contract in self._contracts:
                params: dict[str, object] = {
                    "channel": "trades",
                    "symbol": contract.provider_symbol,
                }
                if contract.after_hours:
                    params["afterHours"] = True
                try:
                    self._websocket.subscribe(params)
                except Exception:  # noqa: BLE001 -- provider SDK exception types are not stable
                    raise FubonFuturesRuntimeError(
                        FubonFuturesRuntimeFailure.SUBSCRIBE_ERROR
                    ) from None
            expected = set(self._by_symbol)
            if not self._wait(
                lambda: set(self._subscription_ids) == expected or self._provider_error,
                self._config.subscribe_timeout_seconds,
            ):
                raise FubonFuturesRuntimeError(FubonFuturesRuntimeFailure.SUBSCRIBE_ACK_TIMEOUT)
            if self._provider_error:
                raise FubonFuturesRuntimeError(FubonFuturesRuntimeFailure.SUBSCRIBE_ERROR)
            if not self._wait(
                lambda: (
                    set(self._quotes) == {item.value for item in FuturesProductCode}
                    or self._provider_error
                ),
                self._config.initial_data_timeout_seconds,
            ):
                raise FubonFuturesRuntimeError(FubonFuturesRuntimeFailure.NO_FRESH_DATA)
            if self._provider_error:
                raise FubonFuturesRuntimeError(FubonFuturesRuntimeFailure.PROVIDER_PAYLOAD_ERROR)
            with self._lock:
                self._status = FubonFuturesRuntimeStatus.READY
        except FubonFuturesRuntimeError:
            self.close()
            raise
        except Exception:  # noqa: BLE001 -- keep provider details outside the runtime boundary
            self.close()
            raise FubonFuturesRuntimeError(FubonFuturesRuntimeFailure.CONNECT_ERROR) from None

    def fetch_latest(self, product_code: str) -> LiveMarketDataRecord | None:
        with self._lock:
            if self._status is not FubonFuturesRuntimeStatus.READY:
                raise LiveMarketDataError(LiveMarketReadStatus.CLIENT_UNAVAILABLE)
            quote = self._quotes.get(product_code)
            contract = next(
                (item for item in self._contracts if item.product_code.value == product_code),
                None,
            )
        if quote is None or contract is None:
            return None
        observed_at = self._clock()
        if observed_at.tzinfo is None or observed_at.utcoffset() is None:
            raise LiveMarketDataError(LiveMarketReadStatus.MALFORMED_PAYLOAD)
        observed_at = max(observed_at, quote.source_timestamp)
        return LiveMarketDataRecord(
            product_code=product_code,
            instrument_name=_PRODUCT_NAMES[contract.product_code],
            contract_code=contract.contract_code,
            contract_month=contract.contract_month,
            source_timestamp=quote.source_timestamp,
            observed_at=observed_at,
            trading_session=(TradingSession.NIGHT if contract.after_hours else TradingSession.DAY),
            market_status="OPEN",
            open=None,
            high=None,
            low=None,
            close=None,
            last_price=quote.last_price,
            volume=quote.volume,
            source_name="fubon-neo-futures-live",
        )

    def list_products(self) -> tuple[str, ...]:
        with self._lock:
            if self._status is not FubonFuturesRuntimeStatus.READY:
                return ()
            return tuple(sorted(self._quotes))

    def close(self) -> None:
        with self._lock:
            if self._status is FubonFuturesRuntimeStatus.CLOSED:
                return
            self._closing = True
            channel_ids = tuple(sorted(self._subscription_ids.values()))
            connected = self._connected
        if channel_ids:
            params: dict[str, object] = (
                {"id": channel_ids[0]} if len(channel_ids) == 1 else {"ids": list(channel_ids)}
            )
            try:
                self._websocket.unsubscribe(params)
                self._wait(
                    lambda: self._unsubscribed_ids.issuperset(channel_ids),
                    self._config.cleanup_timeout_seconds,
                )
            except Exception:  # noqa: BLE001,S110 -- best-effort provider cleanup
                pass
        if connected:
            try:
                self._websocket.disconnect()
            except Exception:  # noqa: BLE001,S110 -- best-effort provider cleanup
                pass
        for event, listener in self._listeners:
            try:
                self._websocket.off(event, listener)
            except Exception:  # noqa: BLE001,S110 -- best-effort listener cleanup
                pass
        with self._lock:
            self._connected = False
            self._status = FubonFuturesRuntimeStatus.CLOSED
        self._changed.set()

    def _build_listeners(self) -> tuple[tuple[str, Callable[..., None]], ...]:
        def connected(*_: object) -> None:
            with self._lock:
                self._connected = True
            self._changed.set()

        def authenticated(*_: object) -> None:
            with self._lock:
                self._authenticated = True
            self._changed.set()

        def provider_error(*_: object) -> None:
            self._fail()

        def disconnected(*_: object) -> None:
            with self._lock:
                self._connected = False
                if not self._closing:
                    self._status = FubonFuturesRuntimeStatus.DEGRADED
            self._changed.set()

        def message(value: str | Mapping[str, Any]) -> None:
            self._on_message(value)

        return (
            ("connect", connected),
            ("authenticated", authenticated),
            ("error", provider_error),
            ("disconnect", disconnected),
            ("message", message),
        )

    def _on_message(self, value: str | Mapping[str, Any]) -> None:
        try:
            message: object = json.loads(value) if isinstance(value, str) else value
            if not isinstance(message, Mapping):
                raise TypeError
            event = message.get("event")
            if event == "authenticated":
                with self._lock:
                    self._authenticated = True
            elif event == "subscribed":
                self._record_subscribed(message.get("data"))
            elif event == "unsubscribed":
                self._record_unsubscribed(message.get("data"))
            elif event == "data" and message.get("channel") == "trades":
                self._record_trade(message.get("data"))
        except (InvalidOperation, OSError, OverflowError, TypeError, ValueError):
            self._fail()
        self._changed.set()

    def _record_subscribed(self, value: object) -> None:
        items = value if isinstance(value, list) else [value]
        for item in items:
            if not isinstance(item, Mapping):
                raise TypeError
            symbol, channel_id = item.get("symbol"), item.get("id")
            if symbol not in self._by_symbol or not isinstance(channel_id, str) or not channel_id:
                raise ValueError
            with self._lock:
                self._subscription_ids[str(symbol)] = channel_id

    def _record_unsubscribed(self, value: object) -> None:
        items = value if isinstance(value, list) else [value]
        for item in items:
            channel_id = item.get("id") if isinstance(item, Mapping) else None
            if not isinstance(channel_id, str):
                raise TypeError
            with self._lock:
                self._unsubscribed_ids.add(channel_id)

    def _record_trade(self, value: object) -> None:
        if not isinstance(value, Mapping):
            raise TypeError
        symbol, trades = value.get("symbol"), value.get("trades")
        contract = self._by_symbol.get(str(symbol))
        if contract is None or not isinstance(trades, list) or not trades:
            raise ValueError
        if not all(
            isinstance(item, Mapping)
            and isinstance(item.get("price"), (int, float))
            and not isinstance(item.get("price"), bool)
            for item in trades
        ):
            raise ValueError
        source_timestamp = _provider_timestamp(value.get("time"))
        observed_at = self._clock()
        if observed_at.tzinfo is None or observed_at.utcoffset() is None:
            raise ValueError
        if (source_timestamp - observed_at).total_seconds() > 5:
            raise ValueError
        sizes = tuple(item.get("size", 0) for item in trades if isinstance(item, Mapping))
        if any(
            not isinstance(size, (int, float)) or isinstance(size, bool) or size < 0
            for size in sizes
        ):
            raise ValueError
        price = Decimal(str(trades[-1]["price"]))
        product = contract.product_code.value
        with self._lock:
            previous = self._quotes.get(product)
            base_volume = (
                previous.volume if previous is not None else Decimal(contract.observed_volume)
            )
            self._quotes[product] = _CachedQuote(
                source_timestamp,
                price,
                base_volume + sum((Decimal(str(size)) for size in sizes), Decimal(0)),
            )

    def _fail(self) -> None:
        with self._lock:
            self._provider_error = True
            if self._status is FubonFuturesRuntimeStatus.READY:
                self._status = FubonFuturesRuntimeStatus.DEGRADED
        self._changed.set()

    def _wait(self, predicate: Callable[[], bool], timeout: float) -> bool:
        deadline = monotonic() + timeout
        while not predicate():
            remaining = deadline - monotonic()
            if remaining <= 0:
                return False
            self._changed.wait(min(0.1, remaining))
            self._changed.clear()
        return True


__all__ = [
    "FubonFuturesLiveClient",
    "FubonFuturesRuntimeConfig",
    "FubonFuturesRuntimeError",
    "FubonFuturesRuntimeFailure",
    "FubonFuturesRuntimeStatus",
]
