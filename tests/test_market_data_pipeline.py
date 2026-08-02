from datetime import UTC, datetime, timedelta
from dataclasses import replace
import inspect

import pytest

from kam_market_ai.market_data import pipeline
from kam_market_ai.market_data.historical_feed import OfflineHistoricalDataset
from kam_market_ai.market_data.provider_adapter import OfflineMarketDataSource, OfflineMarketDataSourceKind
from kam_market_ai.market_data.provider_contract import MarketDataProviderContract, MarketDataTimeframe, ResearchSourceKind
from kam_market_ai.market_data.scan_engine import MarketDataScanRequest, ScanExecutionStatus, build_market_data_scan_plan
from kam_market_ai.market_data.pipeline import (
    OFFLINE_RESEARCH_PIPELINE_VERSION,
    OfflineResearchPipelineVersion,
    run_offline_research_pipeline,
)


NOW = datetime(2026, 8, 9, 10, tzinfo=UTC)


def row(instrument, record_id):
    return {"instrument": instrument, "timeframe": "15m", "opened_at": (NOW - timedelta(minutes=15)).isoformat(), "closed_at": NOW.isoformat(), "open": "100", "high": "102", "low": "99", "close": "101", "volume": "10", "source_record_id": record_id, "closed": True}


def inputs(instruments=("2330", "1101", "1216"), rows=None):
    provider = MarketDataProviderContract("pipeline", "v1", ResearchSourceKind.FIXTURE, (MarketDataTimeframe.M15,))
    dataset = OfflineHistoricalDataset("pipeline-data", "v1", NOW, OfflineMarketDataSource(OfflineMarketDataSourceKind.FIXTURE, tuple(rows or (row("1101", "a"), row("1216", "b"), row("2330", "c")))))
    request = MarketDataScanRequest(provider, dataset, instruments, MarketDataTimeframe.M15, NOW - timedelta(hours=1), NOW + timedelta(hours=1), NOW + timedelta(hours=1), 2)
    return provider, dataset, build_market_data_scan_plan(request)


def test_end_to_end_offline_pipeline_returns_only_scan_and_projection():
    provider, dataset, plan = inputs()
    result = run_offline_research_pipeline(provider, dataset, plan)
    assert result.scan_result.status is ScanExecutionStatus.COMPLETED
    assert result.dashboard_projection.summary.completed_instrument_count == 3
    assert result.canonical_payload()["product_scope"] == "MARKET_RESEARCH_ONLY"


def test_pipeline_serialization_and_hash_are_deterministic_and_input_order_independent():
    first = run_offline_research_pipeline(*inputs())
    second = run_offline_research_pipeline(*inputs(("1216", "2330", "1101")))
    assert first.serialize() == second.serialize()
    assert first.pipeline_hash == second.pipeline_hash


def test_partial_data_remains_completed_with_issues_not_completed():
    provider, dataset, plan = inputs(("1101", "9999"))
    result = run_offline_research_pipeline(provider, dataset, plan)
    assert result.scan_result.status is ScanExecutionStatus.COMPLETED_WITH_ISSUES
    assert result.dashboard_projection.summary.overall_status == "completed_with_issues"
    assert result.dashboard_projection.summary.issue_instrument_count == 1


def test_blocked_offline_source_remains_fail_closed():
    provider, _, _ = inputs()
    dataset = OfflineHistoricalDataset("bad", "v1", NOW, OfflineMarketDataSource(OfflineMarketDataSourceKind.FIXTURE, ({"instrument": "1101"},)))
    plan = build_market_data_scan_plan(MarketDataScanRequest(provider, dataset, ("1101", "1216"), MarketDataTimeframe.M15, NOW - timedelta(hours=1), NOW + timedelta(hours=1), NOW + timedelta(hours=1), 1))
    result = run_offline_research_pipeline(provider, dataset, plan)
    assert result.scan_result.status is ScanExecutionStatus.BLOCKED
    assert result.dashboard_projection.summary.failed_instrument_count == 2


def test_blocked_plan_lineage_mismatch_and_unknown_version_fail_closed():
    provider, dataset, plan = inputs()
    blocked = replace(plan, status=plan.status.BLOCKED)
    with pytest.raises(ValueError, match="Blocked scan plans"):
        run_offline_research_pipeline(provider, dataset, blocked)
    other_provider = replace(provider, provider_id="other-pipeline")
    with pytest.raises(ValueError, match="lineage"):
        run_offline_research_pipeline(other_provider, dataset, plan)
    with pytest.raises(ValueError, match="version matrix"):
        OfflineResearchPipelineVersion(pipeline_version="2.0")


def test_architecture_boundary_has_no_network_or_trading_imports():
    source = inspect.getsource(pipeline).lower()
    for forbidden in ("requests", "urllib", "socket", "websocket", "http", "broker", "order", "account", "position", "trade"):
        assert forbidden not in source


def test_output_is_read_only_and_contains_no_trading_fields():
    provider, dataset, plan = inputs()
    result = run_offline_research_pipeline(provider, dataset, plan)
    with pytest.raises(Exception):
        result.scan_result = None  # type: ignore[misc]
    text = result.serialize().lower()
    for forbidden in ("broker", "order", "account", "position", "margin", "http", "websocket"):
        assert forbidden not in text


def test_pipeline_version_is_fixed():
    assert OFFLINE_RESEARCH_PIPELINE_VERSION == "1.0"
