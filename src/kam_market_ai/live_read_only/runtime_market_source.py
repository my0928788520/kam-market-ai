"""Explicit, fail-closed runtime market source selection."""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from .market_snapshot import MarketDataFreshness, MarketDataReadOnlySource, MarketSnapshot, OFFLINE_DEMO_MARKET_DATA_SOURCE
from .live_market_adapter import FakeLiveMarketDataClient, LiveMarketAdapterConfig, LiveMarketDataAdapter
from .providers.fugle_futures_client import DEFAULT_FUGLE_FUTURES_SYMBOL_REGISTRY, FugleFuturesPayloadMapper
from .providers.fugle_futures_websocket_lifecycle import FakeFugleFuturesWebSocketTransport, FugleFuturesQuoteEnvelope, FugleFuturesWebSocketConfig, FugleFuturesWebSocketLifecycle


class RuntimeMarketSourceMode(StrEnum):
    OFFLINE_DEMO = "offline-demo"
    FAKE_LIVE = "fake-live"
    FUGLE_LIVE_RESERVED = "fugle-live"


class RuntimeMarketSourceStatus(StrEnum):
    READY = "READY"
    DEGRADED = "DEGRADED"
    RESERVED = "RESERVED"


class RuntimeMarketSourceError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class RuntimeMarketSourceConfig:
    mode: RuntimeMarketSourceMode = RuntimeMarketSourceMode.OFFLINE_DEMO


@dataclass(frozen=True, slots=True)
class RuntimeMarketSourceSelection:
    provider: "RuntimeMarketDataProvider"
    mode: RuntimeMarketSourceMode
    status: RuntimeMarketSourceStatus
    source_label: str
    reason_code: str
    is_live_data: bool = False
    is_fake_live: bool = False
    trading_enabled: bool = False


@dataclass(frozen=True, slots=True)
class RuntimeMarketDataProvider:
    source: MarketDataReadOnlySource
    mode: RuntimeMarketSourceMode
    status: RuntimeMarketSourceStatus

    def read_snapshot(self, product_code: str) -> MarketSnapshot:
        return self.source.read_snapshot(product_code) if self.status is RuntimeMarketSourceStatus.READY else self.source.read_snapshot("__RUNTIME_UNAVAILABLE__")

    def list_available_products(self) -> tuple[str, ...]:
        return self.source.list_available_products() if self.status is RuntimeMarketSourceStatus.READY else ()

    def runtime_status(self) -> RuntimeMarketSourceStatus:
        return self.status


class _LifecycleCacheProvider(RuntimeMarketDataProvider):
    lifecycle: FugleFuturesWebSocketLifecycle
    def __init__(self, lifecycle: FugleFuturesWebSocketLifecycle) -> None:
        object.__setattr__(self, "source", OFFLINE_DEMO_MARKET_DATA_SOURCE)
        object.__setattr__(self, "mode", RuntimeMarketSourceMode.FAKE_LIVE)
        object.__setattr__(self, "status", RuntimeMarketSourceStatus.READY)
        object.__setattr__(self, "lifecycle", lifecycle)
    def read_snapshot(self, product_code: str) -> MarketSnapshot:
        record = self.lifecycle.get_latest_record(product_code)
        return LiveMarketDataAdapter(FakeLiveMarketDataClient(()) if record is None else FakeLiveMarketDataClient((record,)), LiveMarketAdapterConfig("fake-live-runtime")).read_snapshot(product_code)
    def list_available_products(self) -> tuple[str, ...]:
        return self.lifecycle.list_ready_products()


class RuntimeMarketSourceSelector:
    def select(self, config: RuntimeMarketSourceConfig = RuntimeMarketSourceConfig()) -> RuntimeMarketSourceSelection:
        if config.mode is RuntimeMarketSourceMode.OFFLINE_DEMO:
            provider = RuntimeMarketDataProvider(OFFLINE_DEMO_MARKET_DATA_SOURCE, config.mode, RuntimeMarketSourceStatus.READY)
            return RuntimeMarketSourceSelection(provider, config.mode, RuntimeMarketSourceStatus.READY, "離線示範行情", "OFFLINE_DEMO")
        if config.mode is RuntimeMarketSourceMode.FAKE_LIVE:
            now = __import__('datetime').datetime(2026, 8, 5, 9, 1, tzinfo=__import__('datetime').UTC)
            lifecycle = FugleFuturesWebSocketLifecycle(FugleFuturesWebSocketConfig(enabled=True), FakeFugleFuturesWebSocketTransport(), clock=lambda: now)
            lifecycle.start()
            mapper = FugleFuturesPayloadMapper(DEFAULT_FUGLE_FUTURES_SYMBOL_REGISTRY, "fake-live-runtime")
            for entry, price, volume in zip(DEFAULT_FUGLE_FUTURES_SYMBOL_REGISTRY.entries, ("24186", "24142", "24108"), ("14872", "39761", "82514"), strict=True):
                raw = {"symbol": entry.provider_symbol, "price": price, "cumulative_volume": volume, "timestamp": "2026-08-05T09:00:59+00:00", "session": "DAY", "market_status": "OPEN"}
                record = mapper.map_payload(entry.product_code, raw, now)
                lifecycle.cache.put(FugleFuturesQuoteEnvelope(record.product_code, record.contract_code, record.source_timestamp, record.observed_at, record.last_price, record.volume, 1, lifecycle.state, MarketDataFreshness.FRESH, record))
            provider = _LifecycleCacheProvider(lifecycle)
            return RuntimeMarketSourceSelection(provider, config.mode, RuntimeMarketSourceStatus.READY, "模擬即時行情", "FAKE_LIVE_READY", is_fake_live=True)
        if config.mode is RuntimeMarketSourceMode.FUGLE_LIVE_RESERVED:
            provider = RuntimeMarketDataProvider(OFFLINE_DEMO_MARKET_DATA_SOURCE, config.mode, RuntimeMarketSourceStatus.RESERVED)
            return RuntimeMarketSourceSelection(provider, config.mode, RuntimeMarketSourceStatus.RESERVED, "真實行情來源尚未啟用", "LIVE_RESERVED")
        raise RuntimeMarketSourceError("INVALID_RUNTIME_SOURCE_MODE")
