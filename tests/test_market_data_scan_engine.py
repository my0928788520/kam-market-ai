from datetime import UTC, datetime, timedelta
import json

import pytest

from kam_market_ai.market_data.historical_feed import OfflineHistoricalDataset
from kam_market_ai.market_data.provider_adapter import OfflineMarketDataSource, OfflineMarketDataSourceKind
from kam_market_ai.market_data.provider_contract import MarketDataProviderContract, MarketDataTimeframe, ResearchSourceKind
from kam_market_ai.market_data.scan_engine import (
    MARKET_DATA_SCAN_ENGINE_VERSION,
    MarketDataScanRequest,
    ScanBatchStatus,
    ScanExecutionStatus,
    ScanPlanStatus,
    build_market_data_scan_plan,
    execute_market_data_scan,
)


NOW = datetime(2026, 8, 6, 10, tzinfo=UTC)


def row(instrument, record_id):
    opened = NOW - timedelta(minutes=15)
    return {"instrument": instrument, "timeframe": "15m", "opened_at": opened.isoformat(), "closed_at": NOW.isoformat(), "open": "100", "high": "102", "low": "99", "close": "101", "volume": "10", "source_record_id": record_id, "closed": True}


def provider(timeframes=(MarketDataTimeframe.M15,)):
    return MarketDataProviderContract("scan-fixture", "v1", ResearchSourceKind.FIXTURE, timeframes)


def dataset(rows=None, kind=OfflineMarketDataSourceKind.FIXTURE):
    content = tuple(rows or (row("1101", "a"), row("1216", "b"), row("2330", "c")))
    return OfflineHistoricalDataset("scan-dataset", "v1", NOW, OfflineMarketDataSource(kind, content))


def request(*, instruments=("2330", "1101", "1216"), batch_size=2, start=NOW - timedelta(hours=1), end=NOW + timedelta(hours=1), as_of=NOW + timedelta(hours=1), timeframes=(MarketDataTimeframe.M15,)):
    return MarketDataScanRequest(provider(timeframes), dataset(), instruments, MarketDataTimeframe.M15, start, end, as_of, batch_size)


def test_plan_canonicalizes_input_order_and_batches_deterministically():
    first = build_market_data_scan_plan(request(instruments=("2330", "1101", "1216")))
    second = build_market_data_scan_plan(request(instruments=("1216", "2330", "1101")))
    assert first.status is ScanPlanStatus.READY and first.plan_hash == second.plan_hash
    assert [(batch.batch_index, batch.instruments) for batch in first.batches] == [(0, ("1101", "1216")), (2, ("2330",))]


def test_complete_scan_uses_historical_feed_and_has_deterministic_hash():
    plan = build_market_data_scan_plan(request())
    first = execute_market_data_scan(plan)
    second = execute_market_data_scan(plan)
    assert first.status is ScanExecutionStatus.COMPLETED
    assert [batch.status for batch in first.batches] == [ScanBatchStatus.COMPLETED, ScanBatchStatus.COMPLETED]
    assert first.scan_hash == second.scan_hash


@pytest.mark.parametrize("kwargs, code", [({"instruments": ()}, "EMPTY_INSTRUMENT_SET"), ({"start": NOW, "end": NOW}, "INVALID_TIME_RANGE"), ({"as_of": NOW - timedelta(hours=2)}, "AS_OF_BEFORE_RANGE"), ({"timeframes": (MarketDataTimeframe.M60,)}, "UNSUPPORTED_TIMEFRAME")])
def test_invalid_plan_inputs_fail_closed(kwargs, code):
    plan = build_market_data_scan_plan(request(**kwargs))
    assert plan.status is ScanPlanStatus.BLOCKED and code in plan.issue_codes
    assert execute_market_data_scan(plan).status is ScanExecutionStatus.BLOCKED


def test_insufficient_offline_data_produces_completed_with_issues():
    scan_request = request(instruments=("1101", "9999"), batch_size=1)
    plan = build_market_data_scan_plan(scan_request)
    result = execute_market_data_scan(plan)
    assert result.status is ScanExecutionStatus.COMPLETED_WITH_ISSUES
    assert [batch.status for batch in result.batches] == [ScanBatchStatus.COMPLETED, ScanBatchStatus.COMPLETED_WITH_ISSUES]
    assert result.batches[1].issue_codes == ("NO_MATCHING_OFFLINE_BARS",)


def test_blocked_source_stops_following_batches_fail_closed():
    blocked_dataset = OfflineHistoricalDataset("bad", "v1", NOW, OfflineMarketDataSource(OfflineMarketDataSourceKind.FIXTURE, ({"instrument": "1101"},)))
    scan_request = MarketDataScanRequest(provider(), blocked_dataset, ("1101", "1216", "2330"), MarketDataTimeframe.M15, NOW - timedelta(hours=1), NOW + timedelta(hours=1), NOW + timedelta(hours=1), 1)
    result = execute_market_data_scan(build_market_data_scan_plan(scan_request))
    assert result.status is ScanExecutionStatus.BLOCKED
    assert [batch.status for batch in result.batches] == [ScanBatchStatus.BLOCKED, ScanBatchStatus.SKIPPED, ScanBatchStatus.SKIPPED]


def test_json_dataset_scan_is_offline_and_hash_stable():
    content = json.dumps([row("1101", "a")])
    json_dataset = OfflineHistoricalDataset("json", "v1", NOW, OfflineMarketDataSource(OfflineMarketDataSourceKind.JSON, content))
    scan_request = MarketDataScanRequest(provider(), json_dataset, ("1101",), MarketDataTimeframe.M15, NOW - timedelta(hours=1), NOW + timedelta(hours=1), NOW + timedelta(hours=1), 1)
    result = execute_market_data_scan(build_market_data_scan_plan(scan_request))
    assert result.status is ScanExecutionStatus.COMPLETED and len(result.batches[0].feeds) == 1


def test_engine_version_is_fixed():
    assert MARKET_DATA_SCAN_ENGINE_VERSION == "1.0"
