from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from kam_market_ai.market_data.dashboard_projection import (
    MARKET_DATA_DASHBOARD_PROJECTION_VERSION,
    MarketDataDashboardInstrument,
    MarketDataDashboardProjection,
    MarketDataDashboardSummary,
    MarketDataDashboardVersion,
    build_market_data_dashboard_projection,
)
from kam_market_ai.market_data.historical_feed import OfflineHistoricalDataset
from kam_market_ai.market_data.provider_adapter import OfflineMarketDataSource, OfflineMarketDataSourceKind
from kam_market_ai.market_data.provider_contract import MarketDataProviderContract, MarketDataTimeframe, ResearchSourceKind
from kam_market_ai.market_data.scan_engine import MarketDataScanRequest, ScanBatchStatus, build_market_data_scan_plan, execute_market_data_scan


NOW = datetime(2026, 8, 8, 10, tzinfo=UTC)


def row(instrument, source_id):
    return {"instrument": instrument, "timeframe": "15m", "opened_at": (NOW - timedelta(minutes=15)).isoformat(), "closed_at": NOW.isoformat(), "open": "100", "high": "102", "low": "99", "close": "101", "volume": "10", "source_record_id": source_id, "closed": True}


def scan_result(instruments=("2330", "1101", "1216")):
    provider = MarketDataProviderContract("projection", "v1", ResearchSourceKind.FIXTURE, (MarketDataTimeframe.M15,))
    dataset = OfflineHistoricalDataset("projection-data", "v1", NOW, OfflineMarketDataSource(OfflineMarketDataSourceKind.FIXTURE, (row("1101", "a"), row("1216", "b"), row("2330", "c"))))
    request = MarketDataScanRequest(provider, dataset, instruments, MarketDataTimeframe.M15, NOW - timedelta(hours=1), NOW + timedelta(hours=1), NOW + timedelta(hours=1), 2)
    return execute_market_data_scan(build_market_data_scan_plan(request))


def test_projection_has_three_second_summary_and_research_boundary():
    projection = build_market_data_dashboard_projection(scan_result())
    assert projection.summary.scanned_instrument_count == 3
    assert projection.summary.completed_instrument_count == 3
    assert projection.canonical_payload()["product_scope"] == "MARKET_RESEARCH_ONLY"
    assert projection.canonical_payload()["network_enabled"] is False


def test_serialization_ordering_and_hash_are_deterministic():
    first = build_market_data_dashboard_projection(scan_result())
    second = build_market_data_dashboard_projection(scan_result(("1216", "2330", "1101")))
    assert first.serialize() == second.serialize()
    assert first.projection_hash == second.projection_hash
    assert [item.instrument for item in first.instruments] == ["1101", "1216", "2330"]


def test_projection_is_immutable():
    projection = build_market_data_dashboard_projection(scan_result())
    with pytest.raises(Exception):
        projection.plan_hash = "changed"  # type: ignore[misc]


def test_version_compatibility_and_source_type_fail_closed():
    with pytest.raises(ValueError, match="Unsupported scan result type"):
        build_market_data_dashboard_projection(object())  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="Unsupported Scan Engine version"):
        build_market_data_dashboard_projection(scan_result(), scan_engine_version="2.0")
    with pytest.raises(ValueError, match="Unsupported Dashboard Projection version"):
        build_market_data_dashboard_projection(scan_result(), projection_version="2.0")


def test_duplicate_instrument_and_contradictory_source_status_fail_closed():
    result = scan_result()
    duplicate_batch = replace(result.batches[1], batch=replace(result.batches[1].batch, instruments=("1101",)))
    with pytest.raises(ValueError, match="unique and canonical"):
        build_market_data_dashboard_projection(replace(result, batches=(result.batches[0], duplicate_batch)))
    blocked = replace(result.batches[0], status=ScanBatchStatus.BLOCKED)
    with pytest.raises(ValueError, match="Completed scan has contradictory"):
        build_market_data_dashboard_projection(replace(result, batches=(blocked, *result.batches[1:])))


def test_illegal_projection_counts_fail_closed():
    version = MarketDataDashboardVersion(MARKET_DATA_DASHBOARD_PROJECTION_VERSION, "1.0")
    summary = MarketDataDashboardSummary("completed", 2, 1, 0, 1)
    with pytest.raises(ValueError, match="instrument counts are contradictory"):
        MarketDataDashboardProjection(version, summary, "plan", "scan", (MarketDataDashboardInstrument("MTX", "completed", "response", "feed", ()),), ())


def test_issue_and_failed_summaries_are_projected_from_offline_scan():
    projection = build_market_data_dashboard_projection(scan_result(("1101", "9999")))
    assert projection.summary.completed_instrument_count == 1
    assert projection.summary.issue_instrument_count == 1
    assert projection.instruments[1].issue_codes == ("NO_MATCHING_OFFLINE_BARS",)


def test_serialized_projection_has_no_live_or_trading_fields():
    text = build_market_data_dashboard_projection(scan_result()).serialize().lower()
    for forbidden in ("broker", "order", "account", "position", "margin", "http", "websocket"):
        assert forbidden not in text
