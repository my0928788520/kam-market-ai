from dataclasses import FrozenInstanceError
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from kam_market_ai.live_read_only.market_snapshot import (
    DEFAULT_MARKET_PRODUCT, OFFLINE_DEMO_MARKET_DATA_SOURCE, MarketDataFreshness,
    MarketDataReadOnlySource, MarketDataSource, MarketSnapshot, MarketSnapshotStatus,
    TradingSession,
)


def test_demo_snapshots_have_independent_tx_mtx_tmf_identity_and_values() -> None:
    source = OFFLINE_DEMO_MARKET_DATA_SOURCE
    snapshots = tuple(source.read_snapshot(code) for code in ("TX", "MTX", "TMF"))
    assert source.list_available_products() == ("MTX", "TMF", "TX")
    assert [(item.product_code, item.instrument_name) for item in snapshots] == [("TX", "臺股期貨"), ("MTX", "小型臺指期貨"), ("TMF", "微型臺指期貨")]
    assert len({item.contract_code for item in snapshots}) == len({item.timestamp for item in snapshots}) == len({item.last_price for item in snapshots}) == len({item.volume for item in snapshots}) == 3
    assert {item.trading_session for item in snapshots} == {TradingSession.DAY, TradingSession.NIGHT, TradingSession.CLOSED}
    assert DEFAULT_MARKET_PRODUCT == "TMF"


def test_invalid_product_contract_and_timestamp_fail_closed() -> None:
    invalid_product = OFFLINE_DEMO_MARKET_DATA_SOURCE.read_snapshot("BAD")
    assert invalid_product.status is MarketSnapshotStatus.INVALID_PRODUCT
    base = OFFLINE_DEMO_MARKET_DATA_SOURCE.read_snapshot("TMF")
    invalid_contract = MarketSnapshot("TMF", "微型臺指期貨", None, None, base.timestamp, base.trading_session, base.market_status, base.open, base.high, base.low, base.close, base.last_price, base.volume, base.data_source, base.freshness, base.status, base.observed_at, base.source_timestamp, base.age_seconds, base.freshness_status)
    assert invalid_contract.status is MarketSnapshotStatus.INVALID_CONTRACT
    invalid_time = MarketSnapshot("TMF", "微型臺指期貨", "TMF202610", "202610", None, TradingSession.UNKNOWN, "UNKNOWN", None, None, None, None, None, None, MarketDataSource.OFFLINE_DEMO, MarketDataFreshness.FRESH, MarketSnapshotStatus.READY, None, None, None, MarketDataFreshness.FRESH)
    assert invalid_time.status is MarketSnapshotStatus.INVALID_TIMESTAMP
    assert invalid_time.freshness is MarketDataFreshness.UNKNOWN


def test_stale_expired_flags_are_fail_closed_and_models_are_immutable() -> None:
    base = OFFLINE_DEMO_MARKET_DATA_SOURCE.read_snapshot("TMF")
    stale = MarketSnapshot(base.product_code, base.instrument_name, base.contract_code, base.contract_month, base.timestamp, base.trading_session, base.market_status, base.open, base.high, base.low, base.close, base.last_price, base.volume, base.data_source, MarketDataFreshness.STALE, MarketSnapshotStatus.READY, base.observed_at, base.source_timestamp, 61, MarketDataFreshness.STALE)
    expired = MarketSnapshot(base.product_code, base.instrument_name, base.contract_code, base.contract_month, base.timestamp, base.trading_session, base.market_status, base.open, base.high, base.low, base.close, base.last_price, base.volume, base.data_source, MarketDataFreshness.EXPIRED, MarketSnapshotStatus.READY, base.observed_at, base.source_timestamp, 601, MarketDataFreshness.EXPIRED)
    assert stale.status is MarketSnapshotStatus.STALE and expired.status is MarketSnapshotStatus.EXPIRED
    with pytest.raises(FrozenInstanceError):
        base.last_price = Decimal("1")  # type: ignore[misc]


def test_serialization_is_deterministic_and_contract_has_no_order_capability() -> None:
    first = OFFLINE_DEMO_MARKET_DATA_SOURCE.read_snapshot("TMF")
    second = OFFLINE_DEMO_MARKET_DATA_SOURCE.read_snapshot("TMF")
    assert first.serialize() == second.serialize() and first.snapshot_hash == second.snapshot_hash
    methods = set(MarketDataReadOnlySource.__dict__)
    for forbidden in ("order", "place_order", "cancel_order", "modify_order", "close_position"):
        assert forbidden not in methods
    assert not first.account_connected and not first.broker_connected
    assert not first.live_order_allowed and not first.trading_enabled
