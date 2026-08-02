from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from kam_market_ai.market_data.provider_contract import (
    MARKET_DATA_PROVIDER_CONTRACT_VERSION,
    MarketDataBar,
    MarketDataProviderContract,
    MarketDataProviderResponse,
    MarketDataRequest,
    MarketDataTimeframe,
    ProviderResponseStatus,
    ResearchSourceKind,
)


NOW = datetime(2026, 8, 3, 10, tzinfo=UTC)


def provider(timeframes=(MarketDataTimeframe.M15,)):
    return MarketDataProviderContract("fixture-mtx", "fixture-v1", ResearchSourceKind.FIXTURE, timeframes)


def request():
    return MarketDataRequest("fixture-mtx", "MTX", MarketDataTimeframe.M15, NOW - timedelta(hours=1), NOW + timedelta(hours=1), NOW)


def bar(*, opened_at=NOW - timedelta(minutes=15), close=Decimal("101"), record_id="record-1"):
    return MarketDataBar("MTX", MarketDataTimeframe.M15, opened_at, opened_at + timedelta(minutes=15), Decimal("100"), Decimal("102"), Decimal("99"), close, Decimal("10"), record_id)


def test_research_only_contract_has_fixed_version_and_offline_flags():
    contract = provider()
    assert contract.contract_version == MARKET_DATA_PROVIDER_CONTRACT_VERSION
    assert contract.research_only is True and contract.network_enabled is False and contract.live_provider_enabled is False


@pytest.mark.parametrize("kwargs", [{"network_enabled": True}, {"live_provider_enabled": True}, {"research_only": False}])
def test_contract_rejects_non_research_capabilities(kwargs):
    with pytest.raises(ValueError, match="research-only and offline"):
        MarketDataProviderContract("fixture-mtx", "fixture-v1", ResearchSourceKind.FIXTURE, (MarketDataTimeframe.M15,), **kwargs)


def test_ready_response_is_canonical_and_hash_is_deterministic():
    response = MarketDataProviderResponse(provider(), request(), ProviderResponseStatus.READY, (bar(),))
    equivalent = MarketDataProviderResponse(provider(), request(), ProviderResponseStatus.READY, (bar(),))
    assert response.canonical_payload()["provider"]["network_enabled"] is False
    assert response.response_hash == equivalent.response_hash


def test_hash_changes_when_market_data_changes():
    first = MarketDataProviderResponse(provider(), request(), ProviderResponseStatus.READY, (bar(),))
    changed = MarketDataProviderResponse(provider(), request(), ProviderResponseStatus.READY, (bar(close=Decimal("101.5")),))
    assert first.response_hash != changed.response_hash


def test_invalid_or_unfinished_bars_fail_closed():
    with pytest.raises(ValueError, match="Only closed research bars"):
        MarketDataProviderResponse(provider(), request(), ProviderResponseStatus.READY, (MarketDataBar("MTX", MarketDataTimeframe.M15, NOW - timedelta(minutes=15), NOW, Decimal("100"), Decimal("102"), Decimal("99"), Decimal("101"), Decimal("10"), "record-1", closed=False),))
    with pytest.raises(ValueError, match="OHLC"):
        MarketDataBar("MTX", MarketDataTimeframe.M15, NOW - timedelta(minutes=15), NOW, Decimal("100"), Decimal("99"), Decimal("98"), Decimal("101"), Decimal("10"), "record-1")


def test_response_rejects_provider_mismatch_unsupported_timeframe_and_noncanonical_bars():
    bad_request = MarketDataRequest("other", "MTX", MarketDataTimeframe.M15, NOW - timedelta(hours=1), NOW + timedelta(hours=1), NOW)
    with pytest.raises(ValueError, match="IDs must match"):
        MarketDataProviderResponse(provider(), bad_request, ProviderResponseStatus.READY, (bar(),))
    with pytest.raises(ValueError, match="strictly canonical"):
        MarketDataProviderResponse(provider(), request(), ProviderResponseStatus.READY, (bar(record_id="b"), bar(record_id="a")))


def test_non_ready_response_requires_canonical_issue_codes():
    with pytest.raises(ValueError, match="require issue codes"):
        MarketDataProviderResponse(provider(), request(), ProviderResponseStatus.BLOCKED, ())
    response = MarketDataProviderResponse(provider(), request(), ProviderResponseStatus.INSUFFICIENT_DATA, (), ("insufficient_history",))
    assert response.canonical_payload()["issue_codes"] == ["insufficient_history"]
