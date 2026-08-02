from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from kam_market_ai.market_data.provider_adapter import (
    MARKET_DATA_PROVIDER_ADAPTER_VERSION,
    OfflineMarketDataSource,
    OfflineMarketDataSourceKind,
    adapt_offline_market_data,
)
from kam_market_ai.market_data.provider_contract import (
    MarketDataProviderContract,
    MarketDataRequest,
    MarketDataTimeframe,
    ProviderResponseStatus,
    ResearchSourceKind,
)


NOW = datetime(2026, 8, 4, 10, tzinfo=UTC)


def provider():
    return MarketDataProviderContract("offline-mtx", "v1", ResearchSourceKind.FIXTURE, (MarketDataTimeframe.M15,))


def request():
    return MarketDataRequest("offline-mtx", "MTX", MarketDataTimeframe.M15, NOW - timedelta(hours=1), NOW + timedelta(hours=1), NOW + timedelta(hours=1))


def row(*, record_id="r1", opened_at=NOW - timedelta(minutes=15), close="101"):
    return {"instrument": "MTX", "timeframe": "15m", "opened_at": opened_at.isoformat(), "closed_at": (opened_at + timedelta(minutes=15)).isoformat(), "open": "100", "high": "102", "low": "99", "close": close, "volume": "10", "source_record_id": record_id, "closed": True}


@pytest.mark.parametrize("kind", [OfflineMarketDataSourceKind.REPLAY, OfflineMarketDataSourceKind.FIXTURE])
def test_replay_and_fixture_sources_adapt_to_ready_response(kind):
    response = adapt_offline_market_data(provider(), request(), OfflineMarketDataSource(kind, (row(),)))
    assert response.status is ProviderResponseStatus.READY
    assert response.bars[0].close == Decimal("101")


def test_json_source_adapts_deterministically():
    import json
    source = OfflineMarketDataSource(OfflineMarketDataSourceKind.JSON, json.dumps([row(record_id="b"), row(record_id="a", opened_at=NOW - timedelta(minutes=30))]))
    first = adapt_offline_market_data(provider(), request(), source)
    second = adapt_offline_market_data(provider(), request(), source)
    assert first.response_hash == second.response_hash
    assert [bar.source_record_id for bar in first.bars] == ["a", "b"]


def test_csv_source_adapts_without_file_or_network_access():
    item = row()
    header = ",".join(item)
    values = ",".join(str(value).lower() if isinstance(value, bool) else str(value) for value in item.values())
    response = adapt_offline_market_data(provider(), request(), OfflineMarketDataSource(OfflineMarketDataSourceKind.CSV, f"{header}\n{values}\n"))
    assert response.status is ProviderResponseStatus.READY


def test_invalid_json_and_malformed_rows_fail_closed():
    invalid_json = adapt_offline_market_data(provider(), request(), OfflineMarketDataSource(OfflineMarketDataSourceKind.JSON, "{"))
    malformed = adapt_offline_market_data(provider(), request(), OfflineMarketDataSource(OfflineMarketDataSourceKind.FIXTURE, ({"instrument": "MTX"},)))
    assert invalid_json.status is ProviderResponseStatus.BLOCKED and invalid_json.issue_codes == ("INVALID_JSON",)
    assert malformed.status is ProviderResponseStatus.BLOCKED and malformed.issue_codes == ("MISSING_REQUIRED_BAR_FIELD",)


def test_empty_or_nonmatching_source_is_insufficient_not_ready():
    response = adapt_offline_market_data(provider(), request(), OfflineMarketDataSource(OfflineMarketDataSourceKind.FIXTURE, (row(opened_at=NOW - timedelta(days=2)),)))
    assert response.status is ProviderResponseStatus.INSUFFICIENT_DATA
    assert response.issue_codes == ("NO_MATCHING_OFFLINE_BARS",)


def test_duplicate_canonical_bar_key_fails_closed():
    response = adapt_offline_market_data(provider(), request(), OfflineMarketDataSource(OfflineMarketDataSourceKind.FIXTURE, (row(), row())))
    assert response.status is ProviderResponseStatus.BLOCKED
    assert response.issue_codes == ("bars must be strictly canonical and unique.",)


def test_source_type_and_adapter_version_are_offline_contract_values():
    assert MARKET_DATA_PROVIDER_ADAPTER_VERSION == "1.0"
    with pytest.raises(ValueError, match="require text content"):
        OfflineMarketDataSource(OfflineMarketDataSourceKind.JSON, (row(),))
