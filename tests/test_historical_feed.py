from datetime import UTC, datetime, timedelta

import json
import pytest

from kam_market_ai.market_data.historical_feed import (
    HISTORICAL_FEED_VERSION,
    OfflineHistoricalDataset,
    read_historical_feed,
)
from kam_market_ai.market_data.provider_adapter import OfflineMarketDataSource, OfflineMarketDataSourceKind
from kam_market_ai.market_data.provider_contract import (
    MarketDataProviderContract,
    MarketDataRequest,
    MarketDataTimeframe,
    ProviderResponseStatus,
    ResearchSourceKind,
)


NOW = datetime(2026, 8, 5, 10, tzinfo=UTC)


def row(*, instrument="MTX", record_id="one"):
    opened = NOW - timedelta(minutes=15)
    return {"instrument": instrument, "timeframe": "15m", "opened_at": opened.isoformat(), "closed_at": NOW.isoformat(), "open": "100", "high": "102", "low": "99", "close": "101", "volume": "10", "source_record_id": record_id, "closed": True}


def request():
    return MarketDataRequest("dataset-provider", "MTX", MarketDataTimeframe.M15, NOW - timedelta(hours=1), NOW + timedelta(hours=1), NOW + timedelta(hours=1))


def provider(kind=ResearchSourceKind.FIXTURE):
    return MarketDataProviderContract("dataset-provider", "v1", kind, (MarketDataTimeframe.M15,))


def dataset(kind=OfflineMarketDataSourceKind.FIXTURE, content=None):
    return OfflineHistoricalDataset("mtx-history", "dataset-v1", NOW, OfflineMarketDataSource(kind, content if content is not None else (row(),)))


@pytest.mark.parametrize("kind", [OfflineMarketDataSourceKind.REPLAY, OfflineMarketDataSourceKind.FIXTURE])
def test_replay_and_fixture_datasets_read_successfully(kind):
    selected_provider = provider(ResearchSourceKind.REPLAY if kind is OfflineMarketDataSourceKind.REPLAY else ResearchSourceKind.FIXTURE)
    result = read_historical_feed(selected_provider, request(), dataset(kind))
    assert result.response.status is ProviderResponseStatus.READY
    assert result.response.bars[0].instrument == "MTX"


@pytest.mark.parametrize("kind", [OfflineMarketDataSourceKind.JSON, OfflineMarketDataSourceKind.CSV])
def test_json_and_csv_datasets_read_successfully(kind):
    if kind is OfflineMarketDataSourceKind.JSON:
        content = json.dumps([row()])
    else:
        item = row(); content = ",".join(item) + "\n" + ",".join(str(value).lower() if isinstance(value, bool) else str(value) for value in item.values()) + "\n"
    result = read_historical_feed(provider(), request(), dataset(kind, content))
    assert result.response.status is ProviderResponseStatus.READY


def test_dataset_hash_is_deterministic_and_mapping_order_independent():
    first = dataset(content=({"instrument": "MTX", **{key: value for key, value in row().items() if key != "instrument"}},))
    second = dataset(content=({key: value for key, value in row().items()},))
    assert first.dataset_hash == second.dataset_hash
    assert read_historical_feed(provider(), request(), first).feed_hash == read_historical_feed(provider(), request(), second).feed_hash


def test_dataset_hash_changes_when_content_changes():
    first = dataset()
    changed = dataset(content=(row(record_id="changed"),))
    assert first.dataset_hash != changed.dataset_hash


def test_source_kind_mismatch_blocks_fail_closed():
    result = read_historical_feed(provider(ResearchSourceKind.REPLAY), request(), dataset(OfflineMarketDataSourceKind.FIXTURE))
    assert result.response.status is ProviderResponseStatus.BLOCKED
    assert result.response.issue_codes == ("DATASET_SOURCE_KIND_MISMATCH",)


def test_invalid_dataset_metadata_or_content_does_not_create_ready_feed():
    with pytest.raises(ValueError, match="timezone-aware"):
        OfflineHistoricalDataset("id", "v1", NOW.replace(tzinfo=None), OfflineMarketDataSource(OfflineMarketDataSourceKind.FIXTURE, (row(),)))
    result = read_historical_feed(provider(), request(), dataset(content=({"instrument": "MTX"},)))
    assert result.response.status is ProviderResponseStatus.BLOCKED


def test_feed_version_is_fixed_and_contains_adapter_response_lineage():
    result = read_historical_feed(provider(), request(), dataset())
    assert result.feed_version == HISTORICAL_FEED_VERSION
    assert result.canonical_payload()["response_hash"] == result.response.response_hash
