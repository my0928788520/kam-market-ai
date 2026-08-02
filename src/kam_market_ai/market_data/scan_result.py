"""Read-only, deterministic projection of offline market-data scan results."""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from json import dumps

from .scan_engine import (
    MARKET_DATA_SCAN_ENGINE_VERSION,
    MarketDataScanResult,
    ScanBatchStatus,
    ScanExecutionStatus,
)


MARKET_DATA_SCAN_RESULT_MODEL_VERSION = "1.0"


def _hash(payload: object) -> str:
    return sha256(dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")).hexdigest()


def _canonical_codes(codes: tuple[str, ...]) -> tuple[str, ...]:
    if any(not isinstance(code, str) or not code for code in codes):
        raise ValueError("issue codes must be non-empty strings.")
    return tuple(sorted(set(codes)))


@dataclass(frozen=True, slots=True)
class ScanFeedReadModel:
    instrument: str
    status: str
    response_hash: str
    feed_hash: str
    issue_codes: tuple[str, ...]

    def canonical_payload(self) -> dict[str, object]:
        return {
            "instrument": self.instrument,
            "status": self.status,
            "response_hash": self.response_hash,
            "feed_hash": self.feed_hash,
            "issue_codes": list(self.issue_codes),
        }


@dataclass(frozen=True, slots=True)
class ScanBatchReadModel:
    batch_index: int
    status: str
    instruments: tuple[str, ...]
    feeds: tuple[ScanFeedReadModel, ...]
    issue_codes: tuple[str, ...]

    def canonical_payload(self) -> dict[str, object]:
        return {
            "batch_index": self.batch_index,
            "status": self.status,
            "instruments": list(self.instruments),
            "feeds": [feed.canonical_payload() for feed in self.feeds],
            "issue_codes": list(self.issue_codes),
        }


@dataclass(frozen=True, slots=True)
class MarketDataScanResultReadModel:
    model_version: str
    source_engine_version: str
    scan_status: str
    plan_status: str
    plan_hash: str
    scan_hash: str
    provider_id: str
    provider_version: str
    dataset_id: str
    dataset_version: str
    dataset_hash: str
    timeframe: str
    requested_instruments: tuple[str, ...]
    batches: tuple[ScanBatchReadModel, ...]

    def canonical_payload(self) -> dict[str, object]:
        return {
            "model_version": self.model_version,
            "source_engine_version": self.source_engine_version,
            "scan_status": self.scan_status,
            "plan_status": self.plan_status,
            "plan_hash": self.plan_hash,
            "scan_hash": self.scan_hash,
            "provider": {"id": self.provider_id, "version": self.provider_version},
            "dataset": {"id": self.dataset_id, "version": self.dataset_version, "hash": self.dataset_hash},
            "timeframe": self.timeframe,
            "requested_instruments": list(self.requested_instruments),
            "batches": [batch.canonical_payload() for batch in self.batches],
            "product_scope": "MARKET_RESEARCH_ONLY",
            "network_enabled": False,
            "live_provider_enabled": False,
        }

    @property
    def result_hash(self) -> str:
        return _hash(self.canonical_payload())

    def serialize(self) -> str:
        return dumps(self.canonical_payload(), sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _validate_result(result: MarketDataScanResult) -> None:
    indices = tuple(batch.batch.batch_index for batch in result.batches)
    if len(indices) != len(set(indices)):
        raise ValueError("scan batches must have unique canonical indexes.")
    statuses = {batch.status for batch in result.batches}
    if ScanBatchStatus.BLOCKED in statuses and result.status is not ScanExecutionStatus.BLOCKED:
        raise ValueError("blocked batch requires blocked scan status.")
    if result.status is ScanExecutionStatus.COMPLETED and any(status is not ScanBatchStatus.COMPLETED for status in statuses):
        raise ValueError("completed scan cannot contain issue, blocked, or skipped batches.")
    if result.status is ScanExecutionStatus.COMPLETED_WITH_ISSUES and ScanBatchStatus.BLOCKED in statuses:
        raise ValueError("issue scan cannot contain blocked batches.")


def build_market_data_scan_result_read_model(
    result: MarketDataScanResult,
    *,
    source_engine_version: str = MARKET_DATA_SCAN_ENGINE_VERSION,
    model_version: str = MARKET_DATA_SCAN_RESULT_MODEL_VERSION,
) -> MarketDataScanResultReadModel:
    """Project an existing scan result without I/O or scan re-execution."""
    if not isinstance(result, MarketDataScanResult):
        raise ValueError("Unsupported scan result type.")
    if source_engine_version != MARKET_DATA_SCAN_ENGINE_VERSION:
        raise ValueError("Unsupported Scan Engine version.")
    if model_version != MARKET_DATA_SCAN_RESULT_MODEL_VERSION:
        raise ValueError("Unsupported Scan Result Model version.")
    _validate_result(result)

    batches = tuple(
        ScanBatchReadModel(
            batch_index=batch_result.batch.batch_index,
            status=batch_result.status.value,
            instruments=tuple(sorted(batch_result.batch.instruments)),
            feeds=tuple(
                sorted(
                    (
                        ScanFeedReadModel(
                            instrument=feed.response.request.instrument,
                            status=feed.response.status.value,
                            response_hash=feed.response.response_hash,
                            feed_hash=feed.feed_hash,
                            issue_codes=_canonical_codes(feed.response.issue_codes),
                        )
                        for feed in batch_result.feeds
                    ),
                    key=lambda feed: (feed.instrument, feed.feed_hash),
                )
            ),
            issue_codes=_canonical_codes(batch_result.issue_codes),
        )
        for batch_result in sorted(result.batches, key=lambda item: item.batch.batch_index)
    )
    request = result.plan.request
    return MarketDataScanResultReadModel(
        model_version=model_version,
        source_engine_version=source_engine_version,
        scan_status=result.status.value,
        plan_status=result.plan.status.value,
        plan_hash=result.plan.plan_hash,
        scan_hash=result.scan_hash,
        provider_id=request.provider.provider_id,
        provider_version=request.provider.provider_version,
        dataset_id=request.dataset.dataset_id,
        dataset_version=request.dataset.dataset_version,
        dataset_hash=request.dataset.dataset_hash,
        timeframe=request.timeframe.value,
        requested_instruments=tuple(sorted({instrument for batch in result.plan.batches for instrument in batch.instruments})),
        batches=batches,
    )


__all__ = [
    "MARKET_DATA_SCAN_RESULT_MODEL_VERSION",
    "MarketDataScanResultReadModel",
    "ScanBatchReadModel",
    "ScanFeedReadModel",
    "build_market_data_scan_result_read_model",
]
