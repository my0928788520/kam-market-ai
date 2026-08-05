"""Fugle futures provider boundary; no connection lifecycle is implemented here."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from re import fullmatch
from typing import Protocol

from ..live_market_adapter import LiveMarketDataError, LiveMarketDataRecord, LiveMarketReadStatus
from ..market_snapshot import TradingSession


class FugleFuturesClientStatus(StrEnum):
    DISABLED = "DISABLED"
    READY = "READY"
    SDK_UNAVAILABLE = "SDK_UNAVAILABLE"
    CLIENT_UNAVAILABLE = "CLIENT_UNAVAILABLE"


class FugleFuturesProviderError(LiveMarketDataError):
    """Provider-neutral failure with no SDK exception detail or credential exposure."""


@dataclass(frozen=True, slots=True)
class FugleFuturesClientConfig:
    api_key: str | None = field(default=None, repr=False)
    enabled: bool = False
    connection_timeout_seconds: int = 5
    read_timeout_seconds: int = 5
    provider_name: str = "fugle-futures-read-only"
    symbol_registry_version: str = "fixture-v1"

    def __post_init__(self) -> None:
        if not self.provider_name or not self.symbol_registry_version:
            raise ValueError("Provider identity is required.")
        if self.connection_timeout_seconds <= 0 or self.read_timeout_seconds <= 0:
            raise ValueError("Read-only timeouts must be positive.")


@dataclass(frozen=True, slots=True)
class FugleFuturesSymbol:
    product_code: str
    provider_symbol: str
    contract_code: str
    contract_month: str
    effective_at: datetime
    source: str
    registry_version: str

    def __post_init__(self) -> None:
        prefixes = {"TX": "TXF", "MTX": "MXF", "TMF": "TMF"}
        if self.product_code not in prefixes or not self.provider_symbol:
            raise ValueError("Unsupported futures product symbol.")
        if not self.contract_code.startswith(prefixes[self.product_code]) or fullmatch(r"20\d{4}", self.contract_month) is None:
            raise ValueError("Invalid futures contract identity.")
        if self.effective_at.tzinfo is None or self.effective_at.utcoffset() is None:
            raise ValueError("Registry timestamp must be timezone-aware.")


@dataclass(frozen=True, slots=True)
class FugleFuturesSymbolRegistry:
    entries: tuple[FugleFuturesSymbol, ...]

    def __post_init__(self) -> None:
        products = tuple(item.product_code for item in self.entries)
        if len(products) != len(set(products)):
            raise ValueError("Duplicate product registry entry.")

    def resolve(self, product_code: str) -> FugleFuturesSymbol | None:
        return next((entry for entry in self.entries if entry.product_code == product_code), None)

    def list_products(self) -> tuple[str, ...]:
        return tuple(sorted(entry.product_code for entry in self.entries))


DEFAULT_FUGLE_FUTURES_SYMBOL_REGISTRY = FugleFuturesSymbolRegistry((
    FugleFuturesSymbol("TX", "TXF202609", "TXF202609", "202609", datetime(2026, 8, 1, tzinfo=UTC), "fixture", "fixture-v1"),
    FugleFuturesSymbol("MTX", "MXF202609", "MXF202609", "202609", datetime(2026, 8, 1, tzinfo=UTC), "fixture", "fixture-v1"),
    FugleFuturesSymbol("TMF", "TMF202610", "TMF202610", "202610", datetime(2026, 8, 1, tzinfo=UTC), "fixture", "fixture-v1"),
))


class FugleFuturesTransportProtocol(Protocol):
    """Synchronous read-only payload seam. Lifecycle work belongs to Sprint 6."""

    def fetch_latest_raw(self, symbol: str) -> object: ...


def _decimal(value: object) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise FugleFuturesProviderError(LiveMarketReadStatus.MALFORMED_PAYLOAD) from None


def _timestamp(value: object) -> datetime:
    if isinstance(value, datetime):
        moment = value
    elif isinstance(value, str):
        try:
            moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            raise FugleFuturesProviderError(LiveMarketReadStatus.MALFORMED_PAYLOAD) from None
    elif isinstance(value, (int, float)) and 946684800 <= value <= 4102444800:
        moment = datetime.fromtimestamp(value, tz=UTC)
    else:
        raise FugleFuturesProviderError(LiveMarketReadStatus.MALFORMED_PAYLOAD)
    if moment.tzinfo is None or moment.utcoffset() is None:
        raise FugleFuturesProviderError(LiveMarketReadStatus.MALFORMED_PAYLOAD)
    return moment


def _session(value: object) -> TradingSession:
    try:
        return TradingSession(str(value))
    except ValueError:
        raise FugleFuturesProviderError(LiveMarketReadStatus.MALFORMED_PAYLOAD) from None


@dataclass(frozen=True, slots=True)
class FugleFuturesPayloadMapper:
    registry: FugleFuturesSymbolRegistry
    provider_name: str

    def map_payload(self, product_code: str, payload: object, observed_at: datetime) -> LiveMarketDataRecord:
        if not isinstance(payload, dict) or observed_at.tzinfo is None or observed_at.utcoffset() is None:
            raise FugleFuturesProviderError(LiveMarketReadStatus.MALFORMED_PAYLOAD)
        identity = self.registry.resolve(product_code)
        if identity is None:
            raise FugleFuturesProviderError(LiveMarketReadStatus.UNSUPPORTED_PRODUCT)
        symbol = payload.get("symbol")
        if symbol != identity.provider_symbol:
            raise FugleFuturesProviderError(LiveMarketReadStatus.MALFORMED_PAYLOAD)
        source_timestamp = _timestamp(payload.get("timestamp"))
        if source_timestamp > observed_at:
            raise FugleFuturesProviderError(LiveMarketReadStatus.MALFORMED_PAYLOAD)
        market_status = payload.get("market_status")
        if market_status not in {"OPEN", "HALTED", "CLOSED"}:
            raise FugleFuturesProviderError(LiveMarketReadStatus.MALFORMED_PAYLOAD)
        session = _session(payload.get("session"))
        price = _decimal(payload.get("price"))
        if price is None:
            raise FugleFuturesProviderError(LiveMarketReadStatus.MALFORMED_PAYLOAD)
        return LiveMarketDataRecord(
            product_code=identity.product_code,
            instrument_name={"TX": "臺股期貨", "MTX": "小型臺指期貨", "TMF": "微型臺指期貨"}[identity.product_code],
            contract_code=identity.contract_code,
            contract_month=identity.contract_month,
            source_timestamp=source_timestamp,
            observed_at=observed_at,
            trading_session=session,
            market_status=str(market_status),
            open=_decimal(payload.get("open")), high=_decimal(payload.get("high")), low=_decimal(payload.get("low")),
            close=_decimal(payload.get("close")), last_price=price,
            volume=_decimal(payload.get("cumulative_volume", payload.get("volume", payload.get("size")))),
            source_name=self.provider_name,
        )


@dataclass(frozen=True, slots=True)
class FakeFugleFuturesTransport:
    """Deterministic no-I/O transport used by unit tests only."""

    payloads: tuple[tuple[str, object], ...] = ()
    timeout_symbols: tuple[str, ...] = ()
    unavailable: bool = False
    authentication_failed: bool = False

    def fetch_latest_raw(self, symbol: str) -> object:
        if self.unavailable or self.authentication_failed:
            raise FugleFuturesProviderError(LiveMarketReadStatus.CLIENT_UNAVAILABLE)
        if symbol in self.timeout_symbols:
            raise TimeoutError
        return next((payload for candidate, payload in self.payloads if candidate == symbol), None)


@dataclass(frozen=True, slots=True)
class FugleFuturesReadOnlyClient:
    """Provider client that does not connect, authenticate, or subscribe in its constructor."""

    config: FugleFuturesClientConfig
    transport: FugleFuturesTransportProtocol | None = None
    registry: FugleFuturesSymbolRegistry = DEFAULT_FUGLE_FUTURES_SYMBOL_REGISTRY

    @property
    def status(self) -> FugleFuturesClientStatus:
        if not self.config.enabled:
            return FugleFuturesClientStatus.DISABLED
        if not self.config.api_key:
            return FugleFuturesClientStatus.CLIENT_UNAVAILABLE
        return FugleFuturesClientStatus.READY

    def fetch_latest(self, product_code: str) -> LiveMarketDataRecord | None:
        if not self.config.enabled or not self.config.api_key or self.transport is None:
            raise FugleFuturesProviderError(LiveMarketReadStatus.CLIENT_UNAVAILABLE)
        identity = self.registry.resolve(product_code)
        if identity is None:
            raise FugleFuturesProviderError(LiveMarketReadStatus.UNSUPPORTED_PRODUCT)
        try:
            payload = self.transport.fetch_latest_raw(identity.provider_symbol)
        except FugleFuturesProviderError:
            raise
        except TimeoutError:
            raise FugleFuturesProviderError(LiveMarketReadStatus.TIMEOUT) from None
        except Exception:
            raise FugleFuturesProviderError(LiveMarketReadStatus.CLIENT_UNAVAILABLE) from None
        if payload is None:
            raise FugleFuturesProviderError(LiveMarketReadStatus.UNSUPPORTED_PRODUCT)
        if not isinstance(payload, dict):
            raise FugleFuturesProviderError(LiveMarketReadStatus.MALFORMED_PAYLOAD)
        observed_at = _timestamp(payload.get("observed_at"))
        return FugleFuturesPayloadMapper(self.registry, self.config.provider_name).map_payload(product_code, payload, observed_at)

    def list_products(self) -> tuple[str, ...]:
        return self.registry.list_products() if self.config.enabled and self.config.api_key else ()


class FugleFuturesSdkFactory:
    """Delayed SDK constructor only; it never connects, authenticates, or subscribes."""

    @staticmethod
    def create_websocket_client(config: FugleFuturesClientConfig) -> object:
        if not config.enabled or not config.api_key:
            raise FugleFuturesProviderError(LiveMarketReadStatus.CLIENT_UNAVAILABLE)
        try:
            from fugle_marketdata import WebSocketClient
        except ImportError:
            raise FugleFuturesProviderError(LiveMarketReadStatus.CLIENT_UNAVAILABLE) from None
        return WebSocketClient(api_key=config.api_key)


__all__ = [
    "DEFAULT_FUGLE_FUTURES_SYMBOL_REGISTRY", "FakeFugleFuturesTransport", "FugleFuturesClientConfig",
    "FugleFuturesClientStatus", "FugleFuturesPayloadMapper", "FugleFuturesProviderError",
    "FugleFuturesReadOnlyClient", "FugleFuturesSdkFactory", "FugleFuturesSymbol",
    "FugleFuturesSymbolRegistry", "FugleFuturesTransportProtocol",
]
