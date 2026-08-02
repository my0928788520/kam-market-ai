from datetime import UTC, datetime, timedelta
from dataclasses import replace

import pytest

from kam_market_ai.market_data.historical_feed import OfflineHistoricalDataset
from kam_market_ai.market_data.provider_adapter import OfflineMarketDataSource, OfflineMarketDataSourceKind
from kam_market_ai.market_data.provider_contract import MarketDataProviderContract, MarketDataTimeframe, ResearchSourceKind
from kam_market_ai.market_data.scan_engine import (
    MarketDataScanRequest,
    ScanBatchStatus,
    ScanExecutionStatus,
    build_market_data_scan_plan,
    execute_market_data_scan,
)
from kam_market_ai.market_data.scan_result import (
    MARKET_DATA_SCAN_RESULT_MODEL_VERSION,
    build_market_data_scan_result_read_model,
)


NOW = datetime(2026, 8, 7, 10, tzinfo=UTC)


def row(instrument, record_id):
    return {"instrument": instrument, "timeframe": "15m", "opened_at": (NOW - timedelta(minutes=15)).isoformat(), "closed_at": NOW.isoformat(), "open": "100", "high": "102", "low": "99", "close": "101", "volume": "10", "source_record_id": record_id, "closed": True}


def scan_result(instruments=("2330", "1101", "1216")):
    provider = MarketDataProviderContract("read-model", "v1", ResearchSourceKind.FIXTURE, (MarketDataTimeframe.M15,))
    dataset = OfflineHistoricalDataset("read-dataset", "v1", NOW, OfflineMarketDataSource(OfflineMarketDataSourceKind.FIXTURE, (row("1101", "a"), row("1216", "b"), row("2330", "c"))))
    request = MarketDataScanRequest(provider, dataset, instruments, MarketDataTimeframe.M15, NOW - timedelta(hours=1), NOW + timedelta(hours=1), NOW + timedelta(hours=1), 2)
    return execute_market_data_scan(build_market_data_scan_plan(request))


def test_read_model_is_immutable_and_contains_scan_lineage():
    model = build_market_data_scan_result_read_model(scan_result())
    assert model.scan_status == "completed" and model.dataset_id == "read-dataset"
    assert model.canonical_payload()["product_scope"] == "MARKET_RESEARCH_ONLY"
    with pytest.raises(Exception):
        model.plan_hash = "changed"  # type: ignore[misc]


def test_serialization_and_result_hash_are_deterministic():
    first = build_market_data_scan_result_read_model(scan_result())
    second = build_market_data_scan_result_read_model(scan_result(instruments=("1216", "2330", "1101")))
    assert first.serialize() == second.serialize()
    assert first.result_hash == second.result_hash


def test_canonical_ordering_ignores_source_batch_order():
    original = scan_result()
    reordered = replace(original, batches=tuple(reversed(original.batches)))
    model = build_market_data_scan_result_read_model(reordered)
    assert [batch.batch_index for batch in model.batches] == [0, 2]
    assert model.requested_instruments == ("1101", "1216", "2330")


def test_result_hash_changes_when_result_content_changes():
    first = build_market_data_scan_result_read_model(scan_result())
    changed = build_market_data_scan_result_read_model(scan_result(instruments=("1101", "1216")))
    assert first.result_hash != changed.result_hash


def test_version_and_type_mismatch_fail_closed():
    with pytest.raises(ValueError, match="Unsupported scan result type"):
        build_market_data_scan_result_read_model(object())  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="Unsupported Scan Engine version"):
        build_market_data_scan_result_read_model(scan_result(), source_engine_version="2.0")
    with pytest.raises(ValueError, match="Unsupported Scan Result Model version"):
        build_market_data_scan_result_read_model(scan_result(), model_version="2.0")


def test_inconsistent_status_and_duplicate_indexes_fail_closed():
    result = scan_result()
    blocked_batch = replace(result.batches[0], status=ScanBatchStatus.BLOCKED)
    with pytest.raises(ValueError, match="blocked batch"):
        build_market_data_scan_result_read_model(replace(result, batches=(blocked_batch, *result.batches[1:])))
    duplicate = replace(result, batches=(result.batches[0], replace(result.batches[1], batch=replace(result.batches[0].batch))))
    with pytest.raises(ValueError, match="unique canonical"):
        build_market_data_scan_result_read_model(duplicate)


def test_read_model_contains_no_live_or_trading_fields():
    model = build_market_data_scan_result_read_model(scan_result())
    text = model.serialize().lower()
    for forbidden in ("broker", "order", "account", "position", "margin", "websocket", "http"):
        assert forbidden not in text


def test_model_version_is_fixed():
    assert MARKET_DATA_SCAN_RESULT_MODEL_VERSION == "1.0"
