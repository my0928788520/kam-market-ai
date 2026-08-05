from datetime import UTC, datetime, timedelta

import pytest

from kam_market_ai.live_read_only.live_market_adapter import LiveMarketDataRecord
from kam_market_ai.live_read_only.market_snapshot import MarketDataFreshness
from kam_market_ai.live_read_only.providers.fugle_futures_client import FugleFuturesClientConfig
from kam_market_ai.live_read_only.providers.fugle_futures_websocket_lifecycle import (
    FakeFugleFuturesWebSocketTransport,
    FugleFuturesConnectionState,
    FugleFuturesLifecycleError,
    FugleFuturesQuoteCache,
    FugleFuturesQuoteEnvelope,
    FugleFuturesReconnectPolicy,
    FugleFuturesWebSocketConfig,
    FugleFuturesWebSocketLifecycle,
)


NOW = datetime(2026, 8, 5, 9, 1, tzinfo=UTC)


def quote(symbol: str = "TXF202609", **changes: object) -> dict[str, object]:
    value: dict[str, object] = {
        "symbol": symbol, "price": "24108", "cumulative_volume": "82514",
        "timestamp": (NOW - timedelta(seconds=1)).isoformat(), "session": "DAY", "market_status": "OPEN",
    }
    value.update(changes)
    return value


def lifecycle(transport: FakeFugleFuturesWebSocketTransport, enabled: bool = True, **changes: object) -> FugleFuturesWebSocketLifecycle:
    config = FugleFuturesWebSocketConfig(
        client=FugleFuturesClientConfig(api_key="TEST_ONLY_TOKEN", enabled=True), enabled=enabled, **changes
    )
    return FugleFuturesWebSocketLifecycle(config, transport, clock=lambda: NOW)


def record(timestamp: datetime) -> LiveMarketDataRecord:
    return LiveMarketDataRecord("TX", "臺股期貨", "TXF202609", "202609", timestamp, timestamp, "DAY", "OPEN", "1", "2", "0", "1", "1", "1", "fixture")


def envelope(timestamp: datetime, sequence: int = 1) -> FugleFuturesQuoteEnvelope:
    item = record(timestamp)
    return FugleFuturesQuoteEnvelope("TX", item.contract_code, timestamp, timestamp, item.last_price, item.volume, sequence, FugleFuturesConnectionState.READY, MarketDataFreshness.FRESH, item)


def test_constructor_and_disabled_mode_do_not_connect() -> None:
    lifecycle_instance = lifecycle(FakeFugleFuturesWebSocketTransport(), enabled=False)
    assert lifecycle_instance.state is FugleFuturesConnectionState.DISABLED
    assert lifecycle_instance.start() is FugleFuturesConnectionState.DISABLED
    assert lifecycle_instance.events == []


def test_legal_happy_path_reaches_ready_and_maps_quote_to_cache() -> None:
    instance = lifecycle(FakeFugleFuturesWebSocketTransport((quote(),)))
    assert instance.start() is FugleFuturesConnectionState.READY
    assert instance.connection_snapshot().subscribed_symbols == ("MXF202609", "TMF202610", "TXF202609")
    assert instance.receive_once() is True
    latest = instance.get_latest_record("TX")
    assert latest is not None and latest.product_code == "TX" and latest.last_price is not None
    assert instance.list_ready_products() == ("TX",)
    assert all(not getattr(instance.connection_snapshot(), flag) for flag in ("account_connected", "broker_connected", "live_order_allowed", "trading_enabled"))


def test_illegal_transition_auth_failure_and_partial_subscription_are_fail_closed() -> None:
    instance = lifecycle(FakeFugleFuturesWebSocketTransport())
    with pytest.raises(FugleFuturesLifecycleError):
        instance._transition(FugleFuturesConnectionState.READY, "BAD")
    assert lifecycle(FakeFugleFuturesWebSocketTransport(authentication_fails=True)).start() is FugleFuturesConnectionState.DEGRADED
    partial = lifecycle(FakeFugleFuturesWebSocketTransport(rejected_symbols=("TMF202610",)))
    assert partial.start() is FugleFuturesConnectionState.DEGRADED
    assert "TMF202610" in partial.connection_snapshot().rejected_symbols
    assert partial.get_latest_record("TX") is None


def test_timeout_malformed_disconnect_and_close_failure_degrade_or_fail_closed() -> None:
    timeout = lifecycle(FakeFugleFuturesWebSocketTransport(receive_timeout=True)); timeout.start()
    assert timeout.receive_once() is False and timeout.state is FugleFuturesConnectionState.DEGRADED
    malformed = lifecycle(FakeFugleFuturesWebSocketTransport((quote(symbol="UNKNOWN"),))); malformed.start()
    assert malformed.receive_once() is False and malformed.state is FugleFuturesConnectionState.DEGRADED
    closed = lifecycle(FakeFugleFuturesWebSocketTransport()); closed.start()
    assert closed.disconnect() is FugleFuturesConnectionState.DISCONNECTED
    broken_close = lifecycle(FakeFugleFuturesWebSocketTransport(close_fails=True)); broken_close.start()
    assert broken_close.disconnect() is FugleFuturesConnectionState.FAILED


def test_reconnect_has_injected_no_sleep_backoff_and_stops_after_limit() -> None:
    sleeps: list[float] = []
    config = FugleFuturesWebSocketConfig(client=FugleFuturesClientConfig(api_key="TEST_ONLY_TOKEN", enabled=True), enabled=True, reconnect_policy=FugleFuturesReconnectPolicy(max_attempts=2, initial_delay_seconds=1, max_delay_seconds=2, multiplier=2))
    instance = FugleFuturesWebSocketLifecycle(config, FakeFugleFuturesWebSocketTransport(connect_fails=True), clock=lambda: NOW, sleeper=sleeps.append)
    assert instance.start() is FugleFuturesConnectionState.DEGRADED
    assert instance.reconnect() is FugleFuturesConnectionState.FAILED
    assert sleeps == [1, 2]


def test_cache_isolated_idempotent_monotonic_and_stale_cache_miss_fails_closed() -> None:
    cache = FugleFuturesQuoteCache(60, 300)
    first = envelope(NOW - timedelta(seconds=1), 1)
    assert cache.put(first) is True and cache.put(first) is False
    assert cache.put(envelope(NOW - timedelta(seconds=2), 2)) is False
    assert cache.get("TX", NOW) is not None and cache.get("TMF", NOW) is None
    assert cache.get("TX", NOW + timedelta(seconds=61)) is None
    assert cache.ready_products(NOW) == ("TX",)


def test_no_trading_capability_or_secret_exposure() -> None:
    instance = lifecycle(FakeFugleFuturesWebSocketTransport())
    forbidden = {"order", "account", "position", "balance", "trade"}
    assert not forbidden & set(FugleFuturesWebSocketLifecycle.__dict__)
    assert "TEST_ONLY_TOKEN" not in repr(instance.config)
    assert all("TEST_ONLY_TOKEN" not in repr(event) for event in instance.events)
