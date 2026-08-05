"""Read-only Fugle futures WebSocket lifecycle; network transport is injected only."""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from enum import StrEnum
from threading import RLock
from typing import Callable, Protocol

from ..live_market_adapter import LiveMarketDataRecord
from ..market_snapshot import MarketDataFreshness
from .fugle_futures_client import (
    DEFAULT_FUGLE_FUTURES_SYMBOL_REGISTRY,
    FugleFuturesClientConfig,
    FugleFuturesPayloadMapper,
    FugleFuturesProviderError,
    FugleFuturesSymbolRegistry,
)


class FugleFuturesConnectionState(StrEnum):
    DISABLED = "DISABLED"
    IDLE = "IDLE"
    CONNECTING = "CONNECTING"
    AUTHENTICATING = "AUTHENTICATING"
    CONNECTED = "CONNECTED"
    SUBSCRIBING = "SUBSCRIBING"
    READY = "READY"
    DEGRADED = "DEGRADED"
    RECONNECT_WAIT = "RECONNECT_WAIT"
    DISCONNECTING = "DISCONNECTING"
    DISCONNECTED = "DISCONNECTED"
    FAILED = "FAILED"


class FugleFuturesSubscriptionState(StrEnum):
    PENDING = "PENDING"
    SUBSCRIBED = "SUBSCRIBED"
    REJECTED = "REJECTED"


class FugleFuturesLifecycleError(RuntimeError):
    """Stable lifecycle error that intentionally contains no provider exception detail."""


@dataclass(frozen=True, slots=True)
class FugleFuturesReconnectPolicy:
    max_attempts: int = 3
    initial_delay_seconds: float = 1.0
    max_delay_seconds: float = 8.0
    multiplier: float = 2.0
    jitter_enabled: bool = False
    reset_after_ready_seconds: int = 60

    def __post_init__(self) -> None:
        if self.max_attempts < 0 or self.initial_delay_seconds < 0 or self.max_delay_seconds < self.initial_delay_seconds or self.multiplier < 1:
            raise ValueError("Invalid deterministic reconnect policy.")

    def delay_for(self, attempt: int) -> float:
        if attempt < 1:
            raise ValueError("Reconnect attempt starts at one.")
        return min(self.max_delay_seconds, self.initial_delay_seconds * self.multiplier ** (attempt - 1))


@dataclass(frozen=True, slots=True)
class FugleFuturesWebSocketConfig:
    client: FugleFuturesClientConfig = field(default_factory=FugleFuturesClientConfig)
    enabled: bool = False
    reconnect_policy: FugleFuturesReconnectPolicy = field(default_factory=FugleFuturesReconnectPolicy)
    required_products: tuple[str, ...] = ("TX", "MTX", "TMF")
    stale_after_seconds: int = 60
    expire_after_seconds: int = 300

    def __post_init__(self) -> None:
        if self.stale_after_seconds < 0 or self.expire_after_seconds < self.stale_after_seconds:
            raise ValueError("Invalid quote freshness configuration.")


@dataclass(frozen=True, slots=True)
class FugleFuturesLifecycleEvent:
    event_type: str
    previous_state: FugleFuturesConnectionState
    current_state: FugleFuturesConnectionState
    timestamp: datetime
    product_code: str | None
    symbol: str | None
    reason_code: str


@dataclass(frozen=True, slots=True)
class FugleFuturesQuoteEnvelope:
    product_code: str
    contract_code: str | None
    source_timestamp: datetime
    observed_at: datetime
    last_price: object
    volume: object
    raw_sequence: int | None
    connection_state: FugleFuturesConnectionState
    freshness: MarketDataFreshness
    record: LiveMarketDataRecord
    account_connected: bool = False
    broker_connected: bool = False
    live_order_allowed: bool = False
    trading_enabled: bool = False


class FugleFuturesWebSocketTransportProtocol(Protocol):
    def connect(self) -> None: ...
    def authenticate(self) -> None: ...
    def subscribe(self, symbols: tuple[str, ...]) -> tuple[str, ...]: ...
    def receive(self) -> object: ...
    def close(self) -> None: ...


class FugleFuturesQuoteCache:
    """Thread-safe in-memory cache with monotonic per-product source timestamps."""

    def __init__(self, stale_after_seconds: int, expire_after_seconds: int) -> None:
        self._stale_after_seconds = stale_after_seconds
        self._expire_after_seconds = expire_after_seconds
        self._items: dict[str, FugleFuturesQuoteEnvelope] = {}
        self._lock = RLock()

    def put(self, envelope: FugleFuturesQuoteEnvelope) -> bool:
        with self._lock:
            existing = self._items.get(envelope.product_code)
            if existing is not None and envelope.source_timestamp <= existing.source_timestamp:
                return False
            self._items[envelope.product_code] = envelope
            return True

    def get(self, product_code: str, now: datetime) -> FugleFuturesQuoteEnvelope | None:
        with self._lock:
            item = self._items.get(product_code)
        if item is None or now.tzinfo is None or now.utcoffset() is None:
            return None
        age = int((now - item.source_timestamp).total_seconds())
        if age < 0:
            return None
        freshness = (MarketDataFreshness.FRESH if age <= self._stale_after_seconds else
                     MarketDataFreshness.STALE if age <= self._expire_after_seconds else
                     MarketDataFreshness.EXPIRED)
        if freshness is not MarketDataFreshness.FRESH:
            return None
        return replace(item, freshness=freshness)

    def ready_products(self, now: datetime) -> tuple[str, ...]:
        with self._lock:
            products = tuple(self._items)
        return tuple(sorted(code for code in products if self.get(code, now) is not None))


@dataclass(frozen=True, slots=True)
class FugleFuturesConnectionSnapshot:
    state: FugleFuturesConnectionState
    requested_symbols: tuple[str, ...]
    subscribed_symbols: tuple[str, ...]
    rejected_symbols: tuple[str, ...]
    subscription_timestamp: datetime | None
    registry_version: str
    account_connected: bool = False
    broker_connected: bool = False
    live_order_allowed: bool = False
    trading_enabled: bool = False


_LEGAL_TRANSITIONS = {
    FugleFuturesConnectionState.IDLE: {FugleFuturesConnectionState.CONNECTING, FugleFuturesConnectionState.DISCONNECTED},
    FugleFuturesConnectionState.CONNECTING: {FugleFuturesConnectionState.AUTHENTICATING, FugleFuturesConnectionState.DEGRADED, FugleFuturesConnectionState.FAILED},
    FugleFuturesConnectionState.AUTHENTICATING: {FugleFuturesConnectionState.CONNECTED, FugleFuturesConnectionState.DEGRADED, FugleFuturesConnectionState.FAILED},
    FugleFuturesConnectionState.CONNECTED: {FugleFuturesConnectionState.SUBSCRIBING, FugleFuturesConnectionState.DISCONNECTING},
    FugleFuturesConnectionState.SUBSCRIBING: {FugleFuturesConnectionState.READY, FugleFuturesConnectionState.DEGRADED, FugleFuturesConnectionState.FAILED},
    FugleFuturesConnectionState.READY: {FugleFuturesConnectionState.DEGRADED, FugleFuturesConnectionState.DISCONNECTING, FugleFuturesConnectionState.RECONNECT_WAIT},
    FugleFuturesConnectionState.DEGRADED: {FugleFuturesConnectionState.RECONNECT_WAIT, FugleFuturesConnectionState.DISCONNECTING, FugleFuturesConnectionState.FAILED},
    FugleFuturesConnectionState.RECONNECT_WAIT: {FugleFuturesConnectionState.CONNECTING, FugleFuturesConnectionState.FAILED},
    FugleFuturesConnectionState.DISCONNECTING: {FugleFuturesConnectionState.DISCONNECTED, FugleFuturesConnectionState.FAILED},
    FugleFuturesConnectionState.DISCONNECTED: {FugleFuturesConnectionState.RECONNECT_WAIT, FugleFuturesConnectionState.CONNECTING},
}


class FugleFuturesWebSocketLifecycle:
    """Explicit, read-only lifecycle. It does no work until `start` is called."""

    def __init__(self, config: FugleFuturesWebSocketConfig, transport: FugleFuturesWebSocketTransportProtocol, registry: FugleFuturesSymbolRegistry = DEFAULT_FUGLE_FUTURES_SYMBOL_REGISTRY, clock: Callable[[], datetime] = lambda: datetime.now(tz=UTC), sleeper: Callable[[float], None] = lambda _delay: None) -> None:
        self.config, self.transport, self.registry, self._clock, self._sleeper = config, transport, registry, clock, sleeper
        self.state = FugleFuturesConnectionState.IDLE if config.enabled else FugleFuturesConnectionState.DISABLED
        self.events: list[FugleFuturesLifecycleEvent] = []
        self.cache = FugleFuturesQuoteCache(config.stale_after_seconds, config.expire_after_seconds)
        self._requested: tuple[str, ...] = ()
        self._subscribed: tuple[str, ...] = ()
        self._rejected: tuple[str, ...] = ()
        self._subscription_timestamp: datetime | None = None

    def _transition(self, next_state: FugleFuturesConnectionState, reason: str, product_code: str | None = None, symbol: str | None = None) -> None:
        if next_state not in _LEGAL_TRANSITIONS.get(self.state, set()):
            raise FugleFuturesLifecycleError("ILLEGAL_STATE_TRANSITION")
        previous = self.state
        self.state = next_state
        self.events.append(FugleFuturesLifecycleEvent("STATE_TRANSITION", previous, next_state, self._clock(), product_code, symbol, reason))

    def start(self) -> FugleFuturesConnectionState:
        if self.state is FugleFuturesConnectionState.DISABLED:
            return self.state
        if self.state not in {FugleFuturesConnectionState.IDLE, FugleFuturesConnectionState.RECONNECT_WAIT, FugleFuturesConnectionState.DISCONNECTED}:
            raise FugleFuturesLifecycleError("START_NOT_ALLOWED")
        try:
            self._transition(FugleFuturesConnectionState.CONNECTING, "START")
            self.transport.connect()
            self._transition(FugleFuturesConnectionState.AUTHENTICATING, "CONNECTED")
            self.transport.authenticate()
            self._transition(FugleFuturesConnectionState.CONNECTED, "AUTHENTICATED")
            entries = tuple(self.registry.resolve(code) for code in self.config.required_products)
            if any(entry is None for entry in entries):
                self._transition(FugleFuturesConnectionState.FAILED, "REGISTRY_INVALID")
                return self.state
            self._requested = tuple(entry.provider_symbol for entry in entries if entry is not None)
            self._transition(FugleFuturesConnectionState.SUBSCRIBING, "SUBSCRIBE_REQUESTED")
            self._subscribed = tuple(sorted(self.transport.subscribe(self._requested)))
            self._rejected = tuple(symbol for symbol in self._requested if symbol not in self._subscribed)
            self._subscription_timestamp = self._clock()
            self._transition(FugleFuturesConnectionState.READY if not self._rejected else FugleFuturesConnectionState.DEGRADED, "SUBSCRIBED" if not self._rejected else "SUBSCRIPTION_PARTIAL")
        except FugleFuturesLifecycleError:
            raise
        except Exception:
            self._transition(FugleFuturesConnectionState.DEGRADED if self.state is not FugleFuturesConnectionState.SUBSCRIBING else FugleFuturesConnectionState.FAILED, "TRANSPORT_FAILURE")
        return self.state

    def receive_once(self) -> bool:
        if self.state is not FugleFuturesConnectionState.READY:
            return False
        try:
            payload = self.transport.receive()
            if not isinstance(payload, dict):
                raise ValueError("malformed payload")
            symbol = payload.get("symbol")
            entry = next((item for item in self.registry.entries if item.provider_symbol == symbol), None)
            if entry is None:
                raise ValueError("unsupported symbol")
            record = FugleFuturesPayloadMapper(self.registry, self.config.client.provider_name).map_payload(entry.product_code, payload, self._clock())
            sequence = payload.get("sequence")
            sequence_number = sequence if isinstance(sequence, int) else None
            envelope = FugleFuturesQuoteEnvelope(record.product_code, record.contract_code, record.source_timestamp, record.observed_at, record.last_price, record.volume, sequence_number, self.state, MarketDataFreshness.FRESH, record)
            return self.cache.put(envelope)
        except Exception:
            self._transition(FugleFuturesConnectionState.DEGRADED, "PAYLOAD_FAILURE")
            return False

    def reconnect(self) -> FugleFuturesConnectionState:
        for attempt in range(1, self.config.reconnect_policy.max_attempts + 1):
            if self.state not in {FugleFuturesConnectionState.DEGRADED, FugleFuturesConnectionState.DISCONNECTED}:
                break
            self._transition(FugleFuturesConnectionState.RECONNECT_WAIT, "RECONNECT")
            self._sleeper(self.config.reconnect_policy.delay_for(attempt))
            if self.start() is FugleFuturesConnectionState.READY:
                return self.state
        if self.state is not FugleFuturesConnectionState.FAILED:
            self._transition(FugleFuturesConnectionState.FAILED, "RECONNECT_EXHAUSTED")
        return self.state

    def disconnect(self) -> FugleFuturesConnectionState:
        if self.state not in {FugleFuturesConnectionState.READY, FugleFuturesConnectionState.DEGRADED, FugleFuturesConnectionState.CONNECTED}:
            return self.state
        self._transition(FugleFuturesConnectionState.DISCONNECTING, "DISCONNECT_REQUESTED")
        try:
            self.transport.close()
            self._transition(FugleFuturesConnectionState.DISCONNECTED, "CLOSED")
        except Exception:
            self._transition(FugleFuturesConnectionState.FAILED, "CLOSE_FAILURE")
        return self.state

    def get_latest_record(self, product_code: str) -> LiveMarketDataRecord | None:
        if self.state is not FugleFuturesConnectionState.READY:
            return None
        envelope = self.cache.get(product_code, self._clock())
        return None if envelope is None else envelope.record

    def list_ready_products(self) -> tuple[str, ...]:
        return () if self.state is not FugleFuturesConnectionState.READY else self.cache.ready_products(self._clock())

    def connection_snapshot(self) -> FugleFuturesConnectionSnapshot:
        return FugleFuturesConnectionSnapshot(self.state, self._requested, self._subscribed, self._rejected, self._subscription_timestamp, self.config.client.symbol_registry_version)


@dataclass(frozen=True, slots=True)
class FakeFugleFuturesWebSocketTransport:
    quotes: tuple[object, ...] = ()
    authentication_fails: bool = False
    rejected_symbols: tuple[str, ...] = ()
    connect_fails: bool = False
    close_fails: bool = False
    receive_timeout: bool = False

    def connect(self) -> None:
        if self.connect_fails:
            raise RuntimeError("connect")

    def authenticate(self) -> None:
        if self.authentication_fails:
            raise RuntimeError("auth")

    def subscribe(self, symbols: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(symbol for symbol in symbols if symbol not in self.rejected_symbols)

    def receive(self) -> object:
        if self.receive_timeout:
            raise TimeoutError
        if not self.quotes:
            raise TimeoutError
        return self.quotes[0]

    def close(self) -> None:
        if self.close_fails:
            raise RuntimeError("close")
