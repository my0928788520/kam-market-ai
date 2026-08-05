"""Read-only live-market adapter boundary with deterministic fake clients.

This module deliberately contains no network client, broker SDK, credential field,
or trading operation.  A future integration may implement the narrow client protocol.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from typing import Protocol, runtime_checkable

from .market_snapshot import (
    DEFAULT_MARKET_PRODUCT,
    OFFLINE_DEMO_MARKET_DATA_SOURCE,
    MarketDataFreshness,
    MarketDataReadOnlySource,
    MarketDataSource,
    MarketSnapshot,
    MarketSnapshotStatus,
    TradingSession,
)


_PRODUCT_NAMES = {"TX": "臺股期貨", "MTX": "小型臺指期貨", "TMF": "微型臺指期貨"}


class LiveMarketConnectionStatus(StrEnum):
    AVAILABLE = "AVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"


class LiveMarketReadStatus(StrEnum):
    READY = "READY"
    CLIENT_UNAVAILABLE = "CLIENT_UNAVAILABLE"
    TIMEOUT = "TIMEOUT"
    MALFORMED_PAYLOAD = "MALFORMED_PAYLOAD"
    UNSUPPORTED_PRODUCT = "UNSUPPORTED_PRODUCT"


class MarketSourceSelection(StrEnum):
    OFFLINE_DEMO = "offline-demo"
    FAKE_LIVE = "fake-live"
    FUTURE_LIVE = "future-live"


class LiveMarketDataError(RuntimeError):
    """Stable, local adapter error; never exposes a provider exception to the UI."""

    def __init__(self, status: LiveMarketReadStatus) -> None:
        self.status = status
        super().__init__(status.value)


@dataclass(frozen=True, slots=True)
class LiveMarketAdapterConfig:
    source_name: str
    source_selection: MarketSourceSelection = MarketSourceSelection.FAKE_LIVE
    stale_after_seconds: int = 60
    expire_after_seconds: int = 300
    data_source: MarketDataSource = MarketDataSource.FAKE_LIVE

    def __post_init__(self) -> None:
        if not self.source_name or self.stale_after_seconds < 0 or self.expire_after_seconds < self.stale_after_seconds:
            raise ValueError("Invalid read-only market adapter configuration.")


@dataclass(frozen=True, slots=True)
class LiveMarketDataRecord:
    product_code: str
    instrument_name: str | None
    contract_code: str | None
    contract_month: str | None
    source_timestamp: datetime | None
    observed_at: datetime | None
    trading_session: TradingSession | str | None
    market_status: str | None
    open: Decimal | str | int | None
    high: Decimal | str | int | None
    low: Decimal | str | int | None
    close: Decimal | str | int | None
    last_price: Decimal | str | int | None
    volume: Decimal | str | int | None
    source_name: str


@runtime_checkable
class LiveMarketDataClientProtocol(Protocol):
    """The only provider-facing capability allowed by the live adapter."""

    def fetch_latest(self, product_code: str) -> LiveMarketDataRecord | object | None: ...

    def list_products(self) -> tuple[str, ...]: ...


@dataclass(frozen=True, slots=True)
class FakeLiveMarketDataClient:
    """Explicit fixture client for tests; it never opens a socket or performs I/O."""

    records: tuple[LiveMarketDataRecord, ...] = ()
    connection_status: LiveMarketConnectionStatus = LiveMarketConnectionStatus.AVAILABLE
    timeout_products: tuple[str, ...] = ()
    malformed_products: tuple[str, ...] = ()

    def fetch_latest(self, product_code: str) -> LiveMarketDataRecord | object | None:
        if self.connection_status is LiveMarketConnectionStatus.UNAVAILABLE:
            raise LiveMarketDataError(LiveMarketReadStatus.CLIENT_UNAVAILABLE)
        if product_code in self.timeout_products:
            raise LiveMarketDataError(LiveMarketReadStatus.TIMEOUT)
        if product_code in self.malformed_products:
            return object()
        return next((record for record in self.records if record.product_code == product_code), None)

    def list_products(self) -> tuple[str, ...]:
        if self.connection_status is LiveMarketConnectionStatus.UNAVAILABLE:
            return ()
        return tuple(sorted(record.product_code for record in self.records))


def _decimal(value: Decimal | str | int | None) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError("Malformed numeric market value.") from None


def _session(value: TradingSession | str | None) -> TradingSession:
    if isinstance(value, TradingSession):
        return value
    try:
        return TradingSession(str(value))
    except ValueError:
        return TradingSession.UNKNOWN


def _status_for_error(status: LiveMarketReadStatus) -> MarketSnapshotStatus:
    return {
        LiveMarketReadStatus.CLIENT_UNAVAILABLE: MarketSnapshotStatus.CLIENT_UNAVAILABLE,
        LiveMarketReadStatus.TIMEOUT: MarketSnapshotStatus.TIMEOUT,
        LiveMarketReadStatus.MALFORMED_PAYLOAD: MarketSnapshotStatus.MALFORMED_PAYLOAD,
        LiveMarketReadStatus.UNSUPPORTED_PRODUCT: MarketSnapshotStatus.INVALID_PRODUCT,
    }[status]


@dataclass(frozen=True, slots=True)
class LiveMarketDataAdapter:
    """Maps a provider-neutral record to the existing immutable MarketSnapshot."""

    client: LiveMarketDataClientProtocol
    config: LiveMarketAdapterConfig

    def _failure_snapshot(self, product_code: str, read_status: LiveMarketReadStatus) -> MarketSnapshot:
        name = _PRODUCT_NAMES.get(product_code, "")
        return MarketSnapshot(
            product_code=product_code,
            instrument_name=name,
            contract_code=None,
            contract_month=None,
            timestamp=None,
            trading_session=TradingSession.UNKNOWN,
            market_status=read_status.value,
            open=None,
            high=None,
            low=None,
            close=None,
            last_price=None,
            volume=None,
            data_source=self.config.data_source,
            freshness=MarketDataFreshness.UNKNOWN,
            status=_status_for_error(read_status),
            observed_at=None,
            source_timestamp=None,
            age_seconds=None,
            freshness_status=MarketDataFreshness.UNKNOWN,
        )

    def read_snapshot(self, product_code: str) -> MarketSnapshot:
        if product_code not in _PRODUCT_NAMES:
            return self._failure_snapshot(product_code, LiveMarketReadStatus.UNSUPPORTED_PRODUCT)
        try:
            record = self.client.fetch_latest(product_code)
        except LiveMarketDataError as error:
            return self._failure_snapshot(product_code, error.status)
        except TimeoutError:
            return self._failure_snapshot(product_code, LiveMarketReadStatus.TIMEOUT)
        except Exception:
            return self._failure_snapshot(product_code, LiveMarketReadStatus.CLIENT_UNAVAILABLE)
        if record is None:
            return self._failure_snapshot(product_code, LiveMarketReadStatus.UNSUPPORTED_PRODUCT)
        if not isinstance(record, LiveMarketDataRecord) or record.product_code != product_code:
            return self._failure_snapshot(product_code, LiveMarketReadStatus.MALFORMED_PAYLOAD)
        try:
            session = _session(record.trading_session)
            if session is TradingSession.UNKNOWN or record.market_status not in {"OPEN", "HALTED", "CLOSED"}:
                return self._failure_snapshot(product_code, LiveMarketReadStatus.MALFORMED_PAYLOAD)
            source_timestamp = record.source_timestamp
            observed_at = record.observed_at
            age = None if source_timestamp is None or observed_at is None else int((observed_at - source_timestamp).total_seconds())
            freshness = (
                MarketDataFreshness.UNKNOWN if age is None or age < 0 else
                MarketDataFreshness.FRESH if age <= self.config.stale_after_seconds else
                MarketDataFreshness.STALE if age <= self.config.expire_after_seconds else
                MarketDataFreshness.EXPIRED
            )
            return MarketSnapshot(
                product_code=record.product_code,
                instrument_name=record.instrument_name or "",
                contract_code=record.contract_code,
                contract_month=record.contract_month,
                timestamp=source_timestamp,
                trading_session=session,
                market_status=record.market_status,
                open=_decimal(record.open), high=_decimal(record.high), low=_decimal(record.low),
                close=_decimal(record.close), last_price=_decimal(record.last_price), volume=_decimal(record.volume),
                data_source=self.config.data_source,
                freshness=freshness,
                status=MarketSnapshotStatus.READY,
                observed_at=observed_at,
                source_timestamp=source_timestamp,
                age_seconds=age,
                freshness_status=freshness,
            )
        except (TypeError, ValueError):
            return self._failure_snapshot(product_code, LiveMarketReadStatus.MALFORMED_PAYLOAD)

    def list_available_products(self) -> tuple[str, ...]:
        try:
            return tuple(sorted(code for code in self.client.list_products() if code in _PRODUCT_NAMES))
        except Exception:
            return ()


def select_market_data_source(
    selection: MarketSourceSelection = MarketSourceSelection.OFFLINE_DEMO,
    live_adapter: LiveMarketDataAdapter | None = None,
) -> MarketDataReadOnlySource:
    """Choose explicitly; no environment variable or implicit live-source activation exists."""
    if selection is MarketSourceSelection.OFFLINE_DEMO:
        return OFFLINE_DEMO_MARKET_DATA_SOURCE
    if live_adapter is None or live_adapter.config.source_selection is not selection:
        raise ValueError("An explicitly configured read-only adapter is required.")
    return live_adapter


__all__ = [
    "FakeLiveMarketDataClient", "LiveMarketAdapterConfig", "LiveMarketConnectionStatus",
    "LiveMarketDataAdapter", "LiveMarketDataClientProtocol", "LiveMarketDataError",
    "LiveMarketDataRecord", "LiveMarketReadStatus", "MarketSourceSelection",
    "select_market_data_source",
]
