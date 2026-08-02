"""Deterministic historical feed over explicitly supplied offline datasets."""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from json import dumps

from .provider_adapter import (
    MARKET_DATA_PROVIDER_ADAPTER_VERSION,
    OfflineMarketDataSource,
    OfflineMarketDataSourceKind,
    adapt_offline_market_data,
)
from .provider_contract import (
    MarketDataProviderContract,
    MarketDataProviderResponse,
    MarketDataRequest,
    ProviderResponseStatus,
    ResearchSourceKind,
)


HISTORICAL_FEED_VERSION = "1.0"


def _utc(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("captured_at must be timezone-aware.")
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _canonical(value: object) -> object:
    if isinstance(value, Mapping):
        return {str(key): _canonical(item) for key, item in sorted(value.items(), key=lambda item: str(item[0]))}
    if isinstance(value, Sequence) and not isinstance(value, str):
        return [_canonical(item) for item in value]
    return value


@dataclass(frozen=True, slots=True)
class OfflineHistoricalDataset:
    dataset_id: str
    dataset_version: str
    captured_at: datetime
    source: OfflineMarketDataSource

    def __post_init__(self) -> None:
        if not self.dataset_id.strip() or not self.dataset_version.strip():
            raise ValueError("dataset_id and dataset_version must be non-empty.")
        _utc(self.captured_at)

    def canonical_payload(self) -> dict[str, object]:
        return {
            "dataset_id": self.dataset_id,
            "dataset_version": self.dataset_version,
            "captured_at": _utc(self.captured_at),
            "source_kind": self.source.source_kind.value,
            "source_version": self.source.source_version,
            "content": _canonical(self.source.content),
        }

    @property
    def dataset_hash(self) -> str:
        payload = dumps(self.canonical_payload(), sort_keys=True, separators=(",", ":"), default=str)
        return sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class HistoricalFeedResult:
    dataset_id: str
    dataset_version: str
    dataset_hash: str
    response: MarketDataProviderResponse
    feed_version: str = HISTORICAL_FEED_VERSION

    def canonical_payload(self) -> dict[str, object]:
        return {
            "feed_version": self.feed_version,
            "dataset_id": self.dataset_id,
            "dataset_version": self.dataset_version,
            "dataset_hash": self.dataset_hash,
            "response": self.response.canonical_payload(),
            "response_hash": self.response.response_hash,
        }

    @property
    def feed_hash(self) -> str:
        payload = dumps(self.canonical_payload(), sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        return sha256(payload.encode("utf-8")).hexdigest()


def _expected_source_kind(source_kind: OfflineMarketDataSourceKind) -> ResearchSourceKind:
    return ResearchSourceKind.REPLAY if source_kind is OfflineMarketDataSourceKind.REPLAY else ResearchSourceKind.FIXTURE


def _blocked(provider: MarketDataProviderContract, request: MarketDataRequest, code: str) -> MarketDataProviderResponse:
    return MarketDataProviderResponse(provider, request, ProviderResponseStatus.BLOCKED, (), (code,))


def read_historical_feed(
    provider: MarketDataProviderContract,
    request: MarketDataRequest,
    dataset: OfflineHistoricalDataset,
) -> HistoricalFeedResult:
    """Read an explicit offline dataset without filesystem or network access."""
    if provider.source_kind is not _expected_source_kind(dataset.source.source_kind):
        response = _blocked(provider, request, "DATASET_SOURCE_KIND_MISMATCH")
    else:
        response = adapt_offline_market_data(provider, request, dataset.source)
    return HistoricalFeedResult(dataset.dataset_id, dataset.dataset_version, dataset.dataset_hash, response)


__all__ = [
    "HISTORICAL_FEED_VERSION",
    "HistoricalFeedResult",
    "OfflineHistoricalDataset",
    "read_historical_feed",
]
