from dataclasses import FrozenInstanceError
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from kam_market_ai.live_read_only.live_market_adapter import (
    FakeLiveMarketDataClient,
    LiveMarketAdapterConfig,
    LiveMarketConnectionStatus,
    LiveMarketDataAdapter,
    LiveMarketDataRecord,
    MarketSourceSelection,
    select_market_data_source,
)
from kam_market_ai.live_read_only.market_snapshot import (
    DEFAULT_MARKET_PRODUCT,
    OFFLINE_DEMO_MARKET_DATA_SOURCE,
    MarketDataReadOnlySource,
    MarketSnapshotStatus,
    TradingSession,
)


NOW = datetime(2026, 8, 5, 9, 0, tzinfo=UTC)


def record(code: str = "TX", age_seconds: int = 0, **changes: object) -> LiveMarketDataRecord:
    values: dict[str, object] = {
        "product_code": code,
        "instrument_name": {"TX": "臺股期貨", "MTX": "小型臺指期貨", "TMF": "微型臺指期貨"}[code],
        "contract_code": {"TX": "TXF202609", "MTX": "MXF202609", "TMF": "TMF202610"}[code],
        "contract_month": "202610" if code == "TMF" else "202609",
        "source_timestamp": NOW - timedelta(seconds=age_seconds),
        "observed_at": NOW,
        "trading_session": TradingSession.DAY,
        "market_status": "OPEN",
        "open": "24000",
        "high": "24100",
        "low": "23900",
        "close": "24080",
        "last_price": "24090",
        "volume": "12345",
        "source_name": "fixture-live-source",
    }
    values.update(changes)
    return LiveMarketDataRecord(**values)  # type: ignore[arg-type]


def adapter(*records: LiveMarketDataRecord, **config_changes: object) -> LiveMarketDataAdapter:
    config = LiveMarketAdapterConfig("fake-live-fixture", **config_changes)  # type: ignore[arg-type]
    return LiveMarketDataAdapter(FakeLiveMarketDataClient(records), config)


def test_adapter_implements_read_only_source_and_maps_independent_products_deterministically() -> None:
    source = adapter(record("TX"), record("MTX", last_price="24111"), record("TMF", last_price="24222"))
    assert isinstance(source, MarketDataReadOnlySource)
    snapshots = tuple(source.read_snapshot(code) for code in ("TX", "MTX", "TMF"))
    assert source.list_available_products() == ("MTX", "TMF", "TX")
    assert [item.product_code for item in snapshots] == ["TX", "MTX", "TMF"]
    assert [item.last_price for item in snapshots] == [Decimal("24090"), Decimal("24111"), Decimal("24222")]
    assert all(item.status is MarketSnapshotStatus.READY for item in snapshots)
    assert snapshots[0].serialize() == source.read_snapshot("TX").serialize()
    assert snapshots[0].snapshot_hash == source.read_snapshot("TX").snapshot_hash
    assert all(not item.account_connected and not item.broker_connected for item in snapshots)
    assert all(not item.live_order_allowed and not item.trading_enabled for item in snapshots)


def test_timeout_malformed_unavailable_and_unsupported_products_fail_closed() -> None:
    timeout = LiveMarketDataAdapter(FakeLiveMarketDataClient((record(),), timeout_products=("TX",)), LiveMarketAdapterConfig("fake"))
    malformed = LiveMarketDataAdapter(FakeLiveMarketDataClient((record(),), malformed_products=("TX",)), LiveMarketAdapterConfig("fake"))
    unavailable = LiveMarketDataAdapter(FakeLiveMarketDataClient(connection_status=LiveMarketConnectionStatus.UNAVAILABLE), LiveMarketAdapterConfig("fake"))
    assert timeout.read_snapshot("TX").status is MarketSnapshotStatus.TIMEOUT
    assert malformed.read_snapshot("TX").status is MarketSnapshotStatus.MALFORMED_PAYLOAD
    assert unavailable.read_snapshot("TX").status is MarketSnapshotStatus.CLIENT_UNAVAILABLE
    assert unavailable.list_available_products() == ()
    assert timeout.read_snapshot("BAD").status is MarketSnapshotStatus.INVALID_PRODUCT


def test_contract_timestamp_session_and_freshness_fail_closed() -> None:
    source = adapter(
        record("TX", contract_code=None, contract_month=None),
        record("MTX", source_timestamp=None),
        record("TMF", age_seconds=61),
    )
    assert source.read_snapshot("TX").status is MarketSnapshotStatus.INVALID_CONTRACT
    assert source.read_snapshot("MTX").status is MarketSnapshotStatus.INVALID_TIMESTAMP
    assert source.read_snapshot("TMF").status is MarketSnapshotStatus.STALE
    assert adapter(record(age_seconds=301)).read_snapshot("TX").status is MarketSnapshotStatus.EXPIRED
    assert adapter(record(trading_session="NOT_A_SESSION")).read_snapshot("TX").status is MarketSnapshotStatus.MALFORMED_PAYLOAD
    reversed_time = adapter(record(source_timestamp=NOW, observed_at=NOW - timedelta(seconds=1))).read_snapshot("TX")
    assert reversed_time.status is MarketSnapshotStatus.INVALID_TIMESTAMP


def test_explicit_source_selection_defaults_to_offline_and_never_auto_enables_live() -> None:
    assert DEFAULT_MARKET_PRODUCT == "TMF"
    assert select_market_data_source() is OFFLINE_DEMO_MARKET_DATA_SOURCE
    live = adapter(record())
    with pytest.raises(ValueError):
        select_market_data_source(MarketSourceSelection.FUTURE_LIVE)
    with pytest.raises(ValueError):
        select_market_data_source(MarketSourceSelection.FUTURE_LIVE, live)
    assert select_market_data_source(MarketSourceSelection.FAKE_LIVE, live) is live


def test_adapter_models_are_immutable_and_expose_no_trading_or_credentials_capability() -> None:
    config = LiveMarketAdapterConfig("fake")
    with pytest.raises(FrozenInstanceError):
        config.source_name = "changed"  # type: ignore[misc]
    names = set(LiveMarketDataAdapter.__dict__) | set(FakeLiveMarketDataClient.__dict__)
    forbidden = {"order", "place_order", "cancel_order", "modify_order", "close_position", "account", "credentials"}
    assert not names & forbidden
    annotations = " ".join(LiveMarketDataRecord.__annotations__)
    for forbidden_name in ("credential", "password", "token", "account"):
        assert forbidden_name not in annotations.lower()
