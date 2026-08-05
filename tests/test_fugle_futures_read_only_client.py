from dataclasses import FrozenInstanceError
from datetime import UTC, datetime, timedelta

import pytest

from kam_market_ai.live_read_only.live_market_adapter import (
    LiveMarketAdapterConfig,
    LiveMarketDataAdapter,
    LiveMarketDataClientProtocol,
)
from kam_market_ai.live_read_only.market_snapshot import MarketSnapshotStatus
from kam_market_ai.live_read_only.providers.fugle_futures_client import (
    DEFAULT_FUGLE_FUTURES_SYMBOL_REGISTRY,
    FakeFugleFuturesTransport,
    FugleFuturesClientConfig,
    FugleFuturesClientStatus,
    FugleFuturesProviderError,
    FugleFuturesReadOnlyClient,
)


NOW = datetime(2026, 8, 5, 9, 1, tzinfo=UTC)


def payload(symbol: str, **changes: object) -> dict[str, object]:
    value: dict[str, object] = {
        "symbol": symbol,
        "price": "24108",
        "cumulative_volume": "82514",
        "timestamp": (NOW - timedelta(seconds=1)).isoformat(),
        "observed_at": NOW.isoformat(),
        "session": "DAY",
        "market_status": "OPEN",
        "open": "24090",
        "high": "24120",
        "low": "24080",
        "close": "24100",
    }
    value.update(changes)
    return value


def client(transport: FakeFugleFuturesTransport, **changes: object) -> FugleFuturesReadOnlyClient:
    values: dict[str, object] = {"api_key": "TEST_ONLY_TOKEN", "enabled": True}
    values.update(changes)
    return FugleFuturesReadOnlyClient(FugleFuturesClientConfig(**values), transport)


def test_constructor_has_no_connect_authenticate_or_subscribe_and_protocol_is_read_only() -> None:
    transport = FakeFugleFuturesTransport()
    source = client(transport)
    assert isinstance(source, LiveMarketDataClientProtocol)
    assert source.status is FugleFuturesClientStatus.READY
    assert transport.payloads == ()
    methods = set(FugleFuturesReadOnlyClient.__dict__) | set(FakeFugleFuturesTransport.__dict__)
    for forbidden in ("place_order", "cancel_order", "modify_order", "close_position", "get_account", "get_balance", "get_positions"):
        assert forbidden not in methods


def test_disabled_or_missing_key_is_fail_closed_and_secret_never_appears_in_repr_or_error() -> None:
    disabled = FugleFuturesReadOnlyClient(FugleFuturesClientConfig(api_key="TEST_ONLY_TOKEN"), FakeFugleFuturesTransport())
    missing = FugleFuturesReadOnlyClient(FugleFuturesClientConfig(enabled=True), FakeFugleFuturesTransport())
    assert disabled.status is FugleFuturesClientStatus.DISABLED and disabled.list_products() == ()
    for source in (disabled, missing):
        with pytest.raises(FugleFuturesProviderError) as error:
            source.fetch_latest("TX")
        assert "TEST_ONLY_TOKEN" not in repr(source) and "TEST_ONLY_TOKEN" not in repr(error.value)


def test_tx_mtx_tmf_payloads_map_to_provider_neutral_records_and_adapter_snapshots() -> None:
    registry = DEFAULT_FUGLE_FUTURES_SYMBOL_REGISTRY
    transport = FakeFugleFuturesTransport(tuple((entry.provider_symbol, payload(entry.provider_symbol)) for entry in registry.entries))
    source = client(transport)
    records = tuple(source.fetch_latest(code) for code in ("TX", "MTX", "TMF"))
    assert [record.product_code for record in records if record] == ["TX", "MTX", "TMF"]
    assert [record.contract_code for record in records if record] == ["TXF202609", "MXF202609", "TMF202610"]
    adapter = LiveMarketDataAdapter(source, LiveMarketAdapterConfig("fugle-fixture"))
    snapshots = tuple(adapter.read_snapshot(code) for code in ("TX", "MTX", "TMF"))
    assert all(snapshot.status is MarketSnapshotStatus.READY for snapshot in snapshots)
    assert all(not snapshot.account_connected and not snapshot.broker_connected for snapshot in snapshots)
    assert all(not snapshot.live_order_allowed and not snapshot.trading_enabled for snapshot in snapshots)


def test_registry_is_deterministic_and_missing_or_unsupported_identity_fails_closed() -> None:
    registry = DEFAULT_FUGLE_FUTURES_SYMBOL_REGISTRY
    assert registry.list_products() == ("MTX", "TMF", "TX")
    assert registry.resolve("BAD") is None
    source = client(FakeFugleFuturesTransport())
    with pytest.raises(FugleFuturesProviderError):
        source.fetch_latest("BAD")
    bad_symbol = client(FakeFugleFuturesTransport((("TXF202609", payload("WRONG")),)))
    adapter = LiveMarketDataAdapter(bad_symbol, LiveMarketAdapterConfig("fugle-fixture"))
    assert adapter.read_snapshot("TX").status is MarketSnapshotStatus.MALFORMED_PAYLOAD


def test_timeout_auth_malformed_timestamp_session_and_status_fail_closed() -> None:
    timeout = client(FakeFugleFuturesTransport(timeout_symbols=("TXF202609",)))
    unavailable = client(FakeFugleFuturesTransport(authentication_failed=True))
    malformed = client(FakeFugleFuturesTransport((("TXF202609", "not-a-dict"),)))
    for source, expected in ((timeout, MarketSnapshotStatus.TIMEOUT), (unavailable, MarketSnapshotStatus.CLIENT_UNAVAILABLE), (malformed, MarketSnapshotStatus.MALFORMED_PAYLOAD)):
        assert LiveMarketDataAdapter(source, LiveMarketAdapterConfig("fugle-fixture")).read_snapshot("TX").status is expected
    missing_timestamp = client(FakeFugleFuturesTransport((("TXF202609", payload("TXF202609", timestamp=None)),)))
    unknown_session = client(FakeFugleFuturesTransport((("TXF202609", payload("TXF202609", session="INVALID")),)))
    unknown_status = client(FakeFugleFuturesTransport((("TXF202609", payload("TXF202609", market_status="UNKNOWN")),)))
    for source in (missing_timestamp, unknown_session, unknown_status):
        assert LiveMarketDataAdapter(source, LiveMarketAdapterConfig("fugle-fixture")).read_snapshot("TX").status is MarketSnapshotStatus.MALFORMED_PAYLOAD


def test_config_is_immutable_and_payload_mapping_is_deterministic_without_sdk_types() -> None:
    config = FugleFuturesClientConfig(api_key="TEST_ONLY_TOKEN", enabled=True)
    with pytest.raises(FrozenInstanceError):
        config.enabled = False  # type: ignore[misc]
    transport = FakeFugleFuturesTransport((("TXF202609", payload("TXF202609")),))
    first = client(transport).fetch_latest("TX")
    second = client(transport).fetch_latest("TX")
    assert first == second
    assert type(first).__module__.startswith("kam_market_ai.live_read_only")
