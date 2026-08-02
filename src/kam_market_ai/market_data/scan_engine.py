"""Deterministic, fail-closed scanning over offline historical datasets."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
from hashlib import sha256
from json import dumps

from .historical_feed import HistoricalFeedResult, OfflineHistoricalDataset, read_historical_feed
from .provider_contract import MarketDataProviderContract, MarketDataRequest, MarketDataTimeframe, ProviderResponseStatus


MARKET_DATA_SCAN_ENGINE_VERSION = "1.0"


class ScanPlanStatus(StrEnum):
    READY = "ready"
    BLOCKED = "blocked"


class ScanBatchStatus(StrEnum):
    COMPLETED = "completed"
    COMPLETED_WITH_ISSUES = "completed_with_issues"
    BLOCKED = "blocked"
    SKIPPED = "skipped"


class ScanExecutionStatus(StrEnum):
    COMPLETED = "completed"
    COMPLETED_WITH_ISSUES = "completed_with_issues"
    BLOCKED = "blocked"


def _utc(value: datetime, field_name: str) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware.")
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _hash(payload: object) -> str:
    return sha256(dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class MarketDataScanRequest:
    provider: MarketDataProviderContract
    dataset: OfflineHistoricalDataset
    instruments: tuple[str, ...]
    timeframe: MarketDataTimeframe
    start_at: datetime
    end_at: datetime
    as_of: datetime
    batch_size: int
    request_version: str = "1.0"

    def __post_init__(self) -> None:
        if self.batch_size <= 0:
            raise ValueError("batch_size must be positive.")
        if not self.request_version.strip():
            raise ValueError("request_version must be non-empty.")
        _utc(self.start_at, "start_at")
        _utc(self.end_at, "end_at")
        _utc(self.as_of, "as_of")


@dataclass(frozen=True, slots=True)
class MarketDataScanBatch:
    batch_index: int
    instruments: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class MarketDataScanPlan:
    status: ScanPlanStatus
    request: MarketDataScanRequest
    batches: tuple[MarketDataScanBatch, ...]
    issue_codes: tuple[str, ...]
    plan_hash: str


@dataclass(frozen=True, slots=True)
class MarketDataScanBatchResult:
    batch: MarketDataScanBatch
    status: ScanBatchStatus
    feeds: tuple[HistoricalFeedResult, ...]
    issue_codes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class MarketDataScanResult:
    plan: MarketDataScanPlan
    status: ScanExecutionStatus
    batches: tuple[MarketDataScanBatchResult, ...]
    scan_hash: str


def _canonical_instruments(instruments: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(sorted({item.strip().upper() for item in instruments if item.strip()}))


def _plan_payload(
    request: MarketDataScanRequest,
    status: ScanPlanStatus,
    batches: tuple[MarketDataScanBatch, ...],
    issue_codes: tuple[str, ...],
) -> dict[str, object]:
    return {
        "engine_version": MARKET_DATA_SCAN_ENGINE_VERSION,
        "status": status.value,
        "provider_id": request.provider.provider_id,
        "provider_version": request.provider.provider_version,
        "dataset_hash": request.dataset.dataset_hash,
        "instruments": [item for batch in batches for item in batch.instruments],
        "timeframe": request.timeframe.value,
        "start_at": _utc(request.start_at, "start_at"),
        "end_at": _utc(request.end_at, "end_at"),
        "as_of": _utc(request.as_of, "as_of"),
        "batch_size": request.batch_size,
        "batches": [{"index": batch.batch_index, "instruments": list(batch.instruments)} for batch in batches],
        "issue_codes": list(issue_codes),
        "request_version": request.request_version,
    }


def build_market_data_scan_plan(request: MarketDataScanRequest) -> MarketDataScanPlan:
    instruments = _canonical_instruments(request.instruments)
    issues: list[str] = []
    if not instruments:
        issues.append("EMPTY_INSTRUMENT_SET")
    if request.start_at >= request.end_at:
        issues.append("INVALID_TIME_RANGE")
    if request.as_of < request.start_at:
        issues.append("AS_OF_BEFORE_RANGE")
    if request.timeframe not in request.provider.supported_timeframes:
        issues.append("UNSUPPORTED_TIMEFRAME")
    status = ScanPlanStatus.BLOCKED if issues else ScanPlanStatus.READY
    batches = () if status is ScanPlanStatus.BLOCKED else tuple(
        MarketDataScanBatch(index, instruments[index:index + request.batch_size])
        for index in range(0, len(instruments), request.batch_size)
    )
    issue_codes = tuple(sorted(set(issues)))
    return MarketDataScanPlan(status, request, batches, issue_codes, _hash(_plan_payload(request, status, batches, issue_codes)))


def _result_payload(plan: MarketDataScanPlan, status: ScanExecutionStatus, batches: tuple[MarketDataScanBatchResult, ...]) -> dict[str, object]:
    return {
        "engine_version": MARKET_DATA_SCAN_ENGINE_VERSION,
        "plan_hash": plan.plan_hash,
        "status": status.value,
        "batches": [
            {
                "index": result.batch.batch_index,
                "status": result.status.value,
                "instruments": list(result.batch.instruments),
                "feed_hashes": [feed.feed_hash for feed in result.feeds],
                "issue_codes": list(result.issue_codes),
            }
            for result in batches
        ],
    }


def _batch_status(feeds: tuple[HistoricalFeedResult, ...]) -> tuple[ScanBatchStatus, tuple[str, ...]]:
    issues = tuple(sorted({code for feed in feeds for code in feed.response.issue_codes}))
    if any(feed.response.status is ProviderResponseStatus.BLOCKED for feed in feeds):
        return ScanBatchStatus.BLOCKED, issues
    if any(feed.response.status is ProviderResponseStatus.INSUFFICIENT_DATA for feed in feeds):
        return ScanBatchStatus.COMPLETED_WITH_ISSUES, issues
    return ScanBatchStatus.COMPLETED, issues


def execute_market_data_scan(plan: MarketDataScanPlan) -> MarketDataScanResult:
    """Execute a plan strictly through the existing in-memory historical feed."""
    if plan.status is ScanPlanStatus.BLOCKED:
        result = MarketDataScanResult(plan, ScanExecutionStatus.BLOCKED, (), "")
        return MarketDataScanResult(plan, result.status, result.batches, _hash(_result_payload(plan, result.status, result.batches)))

    results: list[MarketDataScanBatchResult] = []
    stop = False
    for batch in plan.batches:
        if stop:
            results.append(MarketDataScanBatchResult(batch, ScanBatchStatus.SKIPPED, (), ("PRIOR_BATCH_BLOCKED",)))
            continue
        feeds = tuple(
            read_historical_feed(
                plan.request.provider,
                MarketDataRequest(
                    plan.request.provider.provider_id,
                    instrument,
                    plan.request.timeframe,
                    plan.request.start_at,
                    plan.request.end_at,
                    plan.request.as_of,
                    plan.request.request_version,
                ),
                plan.request.dataset,
            )
            for instrument in batch.instruments
        )
        status, issues = _batch_status(feeds)
        results.append(MarketDataScanBatchResult(batch, status, feeds, issues))
        stop = status is ScanBatchStatus.BLOCKED

    batch_results = tuple(results)
    if any(result.status is ScanBatchStatus.BLOCKED for result in batch_results):
        status = ScanExecutionStatus.BLOCKED
    elif any(result.status is ScanBatchStatus.COMPLETED_WITH_ISSUES for result in batch_results):
        status = ScanExecutionStatus.COMPLETED_WITH_ISSUES
    else:
        status = ScanExecutionStatus.COMPLETED
    return MarketDataScanResult(plan, status, batch_results, _hash(_result_payload(plan, status, batch_results)))


__all__ = [
    "MARKET_DATA_SCAN_ENGINE_VERSION",
    "MarketDataScanBatch",
    "MarketDataScanBatchResult",
    "MarketDataScanPlan",
    "MarketDataScanRequest",
    "MarketDataScanResult",
    "ScanBatchStatus",
    "ScanExecutionStatus",
    "ScanPlanStatus",
    "build_market_data_scan_plan",
    "execute_market_data_scan",
]
