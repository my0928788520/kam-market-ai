"""Deterministic, offline-only futures market snapshot contract."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from hashlib import sha256
from json import dumps
from re import fullmatch
from typing import Protocol, runtime_checkable


DEFAULT_MARKET_PRODUCT = "TMF"
_PRODUCT_NAMES = {"TX": "臺股期貨", "MTX": "小型臺指期貨", "TMF": "微型臺指期貨"}
_CONTRACT_PREFIXES = {"TX": "TXF", "MTX": "MXF", "TMF": "TMF"}


class TradingSession(StrEnum):
    DAY = "DAY"
    NIGHT = "NIGHT"
    CLOSED = "CLOSED"
    UNKNOWN = "UNKNOWN"


class MarketDataFreshness(StrEnum):
    FRESH = "FRESH"
    STALE = "STALE"
    EXPIRED = "EXPIRED"
    UNKNOWN = "UNKNOWN"


class MarketDataSource(StrEnum):
    OFFLINE_DEMO = "OFFLINE_DEMO"
    FAKE_LIVE = "FAKE_LIVE"
    FUTURE_LIVE = "FUTURE_LIVE"


class MarketSnapshotStatus(StrEnum):
    READY = "READY"
    INVALID_PRODUCT = "INVALID_PRODUCT"
    INVALID_CONTRACT = "INVALID_CONTRACT"
    INVALID_TIMESTAMP = "INVALID_TIMESTAMP"
    STALE = "STALE"
    EXPIRED = "EXPIRED"
    UNKNOWN = "UNKNOWN"
    CLIENT_UNAVAILABLE = "CLIENT_UNAVAILABLE"
    TIMEOUT = "TIMEOUT"
    MALFORMED_PAYLOAD = "MALFORMED_PAYLOAD"


@dataclass(frozen=True, slots=True)
class MarketInstrument:
    product_code: str
    instrument_name: str

    def __post_init__(self) -> None:
        if self.product_code not in _PRODUCT_NAMES or self.instrument_name != _PRODUCT_NAMES[self.product_code]:
            raise ValueError("Unsupported futures market instrument.")


@dataclass(frozen=True, slots=True)
class FuturesContractIdentity:
    product_code: str
    contract_code: str
    contract_month: str

    def __post_init__(self) -> None:
        prefix = _CONTRACT_PREFIXES.get(self.product_code)
        if prefix is None or not self.contract_code.startswith(prefix):
            raise ValueError("Contract code does not match product identity.")
        if fullmatch(r"20\d{4}", self.contract_month) is None:
            raise ValueError("Contract month must use YYYYMM.")


def _canonical_json(payload: object) -> str:
    return dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":"))


@dataclass(frozen=True, slots=True)
class MarketSnapshot:
    product_code: str
    instrument_name: str
    contract_code: str | None
    contract_month: str | None
    timestamp: datetime | None
    trading_session: TradingSession
    market_status: str
    open: Decimal | None
    high: Decimal | None
    low: Decimal | None
    close: Decimal | None
    last_price: Decimal | None
    volume: Decimal | None
    data_source: MarketDataSource
    freshness: MarketDataFreshness
    status: MarketSnapshotStatus
    observed_at: datetime | None
    source_timestamp: datetime | None
    age_seconds: int | None
    freshness_status: MarketDataFreshness
    account_connected: bool = False
    broker_connected: bool = False
    live_order_allowed: bool = False
    trading_enabled: bool = False

    def __post_init__(self) -> None:
        status = self.status
        freshness = self.freshness
        terminal_adapter_failure = {
            MarketSnapshotStatus.CLIENT_UNAVAILABLE,
            MarketSnapshotStatus.TIMEOUT,
            MarketSnapshotStatus.MALFORMED_PAYLOAD,
        }
        if status in terminal_adapter_failure:
            freshness = MarketDataFreshness.UNKNOWN
        elif self.product_code not in _PRODUCT_NAMES or self.instrument_name != _PRODUCT_NAMES.get(self.product_code):
            status = MarketSnapshotStatus.INVALID_PRODUCT
        elif self.contract_code is None or self.contract_month is None:
            status = MarketSnapshotStatus.INVALID_CONTRACT
        else:
            try:
                FuturesContractIdentity(self.product_code, self.contract_code, self.contract_month)
            except ValueError:
                status = MarketSnapshotStatus.INVALID_CONTRACT
        if status in terminal_adapter_failure | {MarketSnapshotStatus.INVALID_PRODUCT, MarketSnapshotStatus.INVALID_CONTRACT}:
            pass
        elif self.timestamp is None or self.observed_at is None or self.source_timestamp is None:
            status, freshness = MarketSnapshotStatus.INVALID_TIMESTAMP, MarketDataFreshness.UNKNOWN
        elif any(value.tzinfo is None or value.utcoffset() is None for value in (self.timestamp, self.observed_at, self.source_timestamp)) or self.source_timestamp > self.observed_at:
            status, freshness = MarketSnapshotStatus.INVALID_TIMESTAMP, MarketDataFreshness.UNKNOWN
        elif self.age_seconds is None or self.age_seconds < 0:
            status, freshness = MarketSnapshotStatus.INVALID_TIMESTAMP, MarketDataFreshness.UNKNOWN
        elif self.freshness_status is MarketDataFreshness.EXPIRED or freshness is MarketDataFreshness.EXPIRED:
            status, freshness = MarketSnapshotStatus.EXPIRED, MarketDataFreshness.EXPIRED
        elif self.freshness_status is MarketDataFreshness.STALE or freshness is MarketDataFreshness.STALE:
            status, freshness = MarketSnapshotStatus.STALE, MarketDataFreshness.STALE
        elif self.freshness_status is MarketDataFreshness.UNKNOWN or freshness is MarketDataFreshness.UNKNOWN:
            status, freshness = MarketSnapshotStatus.UNKNOWN, MarketDataFreshness.UNKNOWN
        if self.account_connected or self.broker_connected or self.live_order_allowed or self.trading_enabled:
            raise ValueError("Live account, broker, and trading flags must remain false.")
        object.__setattr__(self, "status", status)
        object.__setattr__(self, "freshness", freshness)
        object.__setattr__(self, "freshness_status", freshness)

    def canonical_payload(self) -> dict[str, object]:
        return {
            "account_connected": self.account_connected,
            "age_seconds": self.age_seconds,
            "broker_connected": self.broker_connected,
            "close": None if self.close is None else str(self.close),
            "contract_code": self.contract_code,
            "contract_month": self.contract_month,
            "data_source": self.data_source.value,
            "freshness": self.freshness.value,
            "freshness_status": self.freshness_status.value,
            "high": None if self.high is None else str(self.high),
            "instrument_name": self.instrument_name,
            "last_price": None if self.last_price is None else str(self.last_price),
            "live_order_allowed": self.live_order_allowed,
            "low": None if self.low is None else str(self.low),
            "market_status": self.market_status,
            "observed_at": None if self.observed_at is None else self.observed_at.isoformat(),
            "open": None if self.open is None else str(self.open),
            "product_code": self.product_code,
            "source_timestamp": None if self.source_timestamp is None else self.source_timestamp.isoformat(),
            "status": self.status.value,
            "timestamp": None if self.timestamp is None else self.timestamp.isoformat(),
            "trading_enabled": self.trading_enabled,
            "trading_session": self.trading_session.value,
            "volume": None if self.volume is None else str(self.volume),
        }

    def serialize(self) -> str:
        return _canonical_json(self.canonical_payload())

    @property
    def snapshot_hash(self) -> str:
        return sha256(self.serialize().encode("utf-8")).hexdigest()


@runtime_checkable
class MarketDataReadOnlySource(Protocol):
    def read_snapshot(self, product_code: str) -> MarketSnapshot: ...

    def list_available_products(self) -> tuple[str, ...]: ...


def _invalid_product_snapshot(product_code: str) -> MarketSnapshot:
    return MarketSnapshot(product_code, "", None, None, None, TradingSession.UNKNOWN, "UNKNOWN", None, None, None, None, None, None, MarketDataSource.OFFLINE_DEMO, MarketDataFreshness.UNKNOWN, MarketSnapshotStatus.INVALID_PRODUCT, None, None, None, MarketDataFreshness.UNKNOWN)


@dataclass(frozen=True, slots=True)
class OfflineDemoMarketDataSource:
    """Explicit fixed data for local contract tests; it performs no I/O."""
    snapshots: tuple[MarketSnapshot, ...]

    def __post_init__(self) -> None:
        codes = tuple(item.product_code for item in self.snapshots)
        if tuple(sorted(codes)) != ("MTX", "TMF", "TX") or len(codes) != len(set(codes)):
            raise ValueError("Offline demo source must contain independent TX, MTX, and TMF snapshots.")

    def read_snapshot(self, product_code: str) -> MarketSnapshot:
        return next((item for item in self.snapshots if item.product_code == product_code), _invalid_product_snapshot(product_code))

    def list_available_products(self) -> tuple[str, ...]:
        return tuple(sorted(item.product_code for item in self.snapshots))


def _demo_snapshot(code: str, name: str, contract: str, month: str, timestamp: str, session: TradingSession, status: str, price: str, volume: str) -> MarketSnapshot:
    moment = datetime.fromisoformat(timestamp)
    last = Decimal(price)
    return MarketSnapshot(code, name, contract, month, moment, session, status, last - Decimal("18"), last + Decimal("24"), last - Decimal("31"), last - Decimal("4"), last, Decimal(volume), MarketDataSource.OFFLINE_DEMO, MarketDataFreshness.FRESH, MarketSnapshotStatus.READY, moment, moment, 0, MarketDataFreshness.FRESH)


OFFLINE_DEMO_MARKET_DATA_SOURCE = OfflineDemoMarketDataSource((
    _demo_snapshot("TX", "臺股期貨", "TXF202609", "202609", "2026-08-05T09:01:00+00:00", TradingSession.DAY, "OPEN", "24186", "14872"),
    _demo_snapshot("MTX", "小型臺指期貨", "MXF202609", "202609", "2026-08-05T17:46:00+00:00", TradingSession.NIGHT, "HALTED", "24142", "39761"),
    _demo_snapshot("TMF", "微型臺指期貨", "TMF202610", "202610", "2026-08-06T02:14:00+00:00", TradingSession.CLOSED, "CLOSED", "24108", "82514"),
))


__all__ = [
    "DEFAULT_MARKET_PRODUCT", "FuturesContractIdentity", "MarketDataFreshness",
    "MarketDataReadOnlySource", "MarketDataSource", "MarketInstrument", "MarketSnapshot",
    "MarketSnapshotStatus", "OFFLINE_DEMO_MARKET_DATA_SOURCE", "OfflineDemoMarketDataSource",
    "TradingSession",
]
