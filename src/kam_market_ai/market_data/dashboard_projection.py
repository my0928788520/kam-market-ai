"""Read-only dashboard projection for deterministic offline scan results."""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from json import dumps

from .provider_contract import ProviderResponseStatus
from .scan_engine import (
    MARKET_DATA_SCAN_ENGINE_VERSION,
    MarketDataScanResult,
    ScanBatchStatus,
    ScanExecutionStatus,
)


MARKET_DATA_DASHBOARD_PROJECTION_VERSION = "1.0"


def _hash(payload: object) -> str:
    return sha256(dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class MarketDataDashboardVersion:
    projection_version: str
    scan_engine_version: str

    def __post_init__(self) -> None:
        if self.projection_version != MARKET_DATA_DASHBOARD_PROJECTION_VERSION:
            raise ValueError("Unsupported Dashboard Projection version.")
        if self.scan_engine_version != MARKET_DATA_SCAN_ENGINE_VERSION:
            raise ValueError("Unsupported Scan Engine version.")


@dataclass(frozen=True, slots=True)
class MarketDataDashboardSummary:
    overall_status: str
    scanned_instrument_count: int
    completed_instrument_count: int
    failed_instrument_count: int
    issue_instrument_count: int

    def __post_init__(self) -> None:
        counts = (
            self.scanned_instrument_count,
            self.completed_instrument_count,
            self.failed_instrument_count,
            self.issue_instrument_count,
        )
        if any(not isinstance(value, int) or value < 0 for value in counts):
            raise ValueError("Dashboard counts must be non-negative integers.")
        if self.scanned_instrument_count != sum(counts[1:]):
            raise ValueError("Dashboard counts are contradictory.")
        if self.overall_status not in {item.value for item in ScanExecutionStatus}:
            raise ValueError("Unknown dashboard overall status.")


@dataclass(frozen=True, slots=True)
class MarketDataDashboardInstrument:
    instrument: str
    status: str
    response_hash: str | None
    feed_hash: str | None
    issue_codes: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.instrument or self.instrument != self.instrument.strip().upper():
            raise ValueError("Instrument must be canonical.")
        if self.status not in {"completed", "failed", "issue"}:
            raise ValueError("Unknown dashboard instrument status.")
        if tuple(sorted(set(self.issue_codes))) != self.issue_codes or any(not item for item in self.issue_codes):
            raise ValueError("Instrument issue codes must be canonical.")
        if self.status == "completed" and (self.issue_codes or not self.response_hash or not self.feed_hash):
            raise ValueError("Completed instruments require hashes and no issues.")
        if self.status != "completed" and (self.response_hash is None) != (self.feed_hash is None):
            raise ValueError("Instrument hashes must be both present or both absent.")


@dataclass(frozen=True, slots=True)
class MarketDataDashboardIssue:
    code: str
    instrument: str | None
    severity: str

    def __post_init__(self) -> None:
        if not self.code or self.severity not in {"issue", "failed"}:
            raise ValueError("Invalid dashboard issue.")
        if self.instrument is not None and self.instrument != self.instrument.strip().upper():
            raise ValueError("Issue instrument must be canonical.")


@dataclass(frozen=True, slots=True)
class MarketDataDashboardProjection:
    version: MarketDataDashboardVersion
    summary: MarketDataDashboardSummary
    plan_hash: str
    scan_hash: str
    instruments: tuple[MarketDataDashboardInstrument, ...]
    issues: tuple[MarketDataDashboardIssue, ...]

    def __post_init__(self) -> None:
        if not self.plan_hash or not self.scan_hash:
            raise ValueError("Projection requires plan and scan hashes.")
        instruments = tuple(item.instrument for item in self.instruments)
        if instruments != tuple(sorted(set(instruments))):
            raise ValueError("Dashboard instruments must be unique and canonical ordered.")
        expected = {
            "completed": self.summary.completed_instrument_count,
            "failed": self.summary.failed_instrument_count,
            "issue": self.summary.issue_instrument_count,
        }
        actual = {status: sum(item.status == status for item in self.instruments) for status in expected}
        if len(self.instruments) != self.summary.scanned_instrument_count or actual != expected:
            raise ValueError("Dashboard instrument counts are contradictory.")
        issue_keys = tuple((item.instrument or "", item.severity, item.code) for item in self.issues)
        if issue_keys != tuple(sorted(set(issue_keys))):
            raise ValueError("Dashboard issues must be unique and canonical ordered.")

    def canonical_payload(self) -> dict[str, object]:
        return {
            "version": {
                "projection_version": self.version.projection_version,
                "scan_engine_version": self.version.scan_engine_version,
            },
            "summary": {
                "overall_status": self.summary.overall_status,
                "scanned_instrument_count": self.summary.scanned_instrument_count,
                "completed_instrument_count": self.summary.completed_instrument_count,
                "failed_instrument_count": self.summary.failed_instrument_count,
                "issue_instrument_count": self.summary.issue_instrument_count,
            },
            "plan_hash": self.plan_hash,
            "scan_hash": self.scan_hash,
            "instruments": [
                {"instrument": item.instrument, "status": item.status, "response_hash": item.response_hash, "feed_hash": item.feed_hash, "issue_codes": list(item.issue_codes)}
                for item in self.instruments
            ],
            "issues": [
                {"code": item.code, "instrument": item.instrument, "severity": item.severity}
                for item in self.issues
            ],
            "product_scope": "MARKET_RESEARCH_ONLY",
            "network_enabled": False,
            "live_provider_enabled": False,
        }

    @property
    def projection_hash(self) -> str:
        return _hash(self.canonical_payload())

    def serialize(self) -> str:
        return dumps(self.canonical_payload(), sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _instrument_from_feed(feed) -> MarketDataDashboardInstrument:
    response = feed.response
    if response.status is ProviderResponseStatus.READY:
        return MarketDataDashboardInstrument(response.request.instrument, "completed", response.response_hash, feed.feed_hash, ())
    status = "failed" if response.status is ProviderResponseStatus.BLOCKED else "issue"
    return MarketDataDashboardInstrument(
        response.request.instrument,
        status,
        response.response_hash,
        feed.feed_hash,
        tuple(sorted(set(response.issue_codes))),
    )


def _validate_source_result(result: MarketDataScanResult) -> None:
    expected_instruments = tuple(item for batch in result.plan.batches for item in batch.instruments)
    if expected_instruments != tuple(sorted(set(expected_instruments))):
        raise ValueError("Scan plan instruments must be unique and canonical ordered.")
    result_instruments = tuple(item for batch_result in result.batches for item in batch_result.batch.instruments)
    if len(result_instruments) != len(set(result_instruments)):
        raise ValueError("Scan result instruments must be unique and canonical.")
    by_index = {batch.batch_index: batch for batch in result.plan.batches}
    seen: set[str] = set()
    for batch_result in result.batches:
        if batch_result.batch.batch_index not in by_index or batch_result.batch != by_index[batch_result.batch.batch_index]:
            raise ValueError("Scan result batch is not part of its plan.")
        feed_instruments = tuple(feed.response.request.instrument for feed in batch_result.feeds)
        if len(feed_instruments) != len(set(feed_instruments)) or any(item not in batch_result.batch.instruments for item in feed_instruments):
            raise ValueError("Scan result contains duplicate or invalid feed instruments.")
        if batch_result.status is ScanBatchStatus.SKIPPED and batch_result.feeds:
            raise ValueError("Skipped scan batch cannot contain feeds.")
        if batch_result.status is not ScanBatchStatus.SKIPPED and set(feed_instruments) != set(batch_result.batch.instruments):
            raise ValueError("Non-skipped scan batch must contain every planned instrument.")
        seen.update(feed_instruments)
    if result.status is ScanExecutionStatus.COMPLETED and any(batch.status is not ScanBatchStatus.COMPLETED for batch in result.batches):
        raise ValueError("Completed scan has contradictory batch statuses.")
    if result.status is ScanExecutionStatus.BLOCKED and not any(batch.status is ScanBatchStatus.BLOCKED for batch in result.batches):
        raise ValueError("Blocked scan requires a blocked batch.")


def build_market_data_dashboard_projection(
    result: MarketDataScanResult,
    *,
    scan_engine_version: str = MARKET_DATA_SCAN_ENGINE_VERSION,
    projection_version: str = MARKET_DATA_DASHBOARD_PROJECTION_VERSION,
) -> MarketDataDashboardProjection:
    """Project an existing offline scan result; no scan or external I/O occurs."""
    if not isinstance(result, MarketDataScanResult):
        raise ValueError("Unsupported scan result type.")
    version = MarketDataDashboardVersion(projection_version, scan_engine_version)
    _validate_source_result(result)
    by_index = {item.batch.batch_index: item for item in result.batches}
    instruments: list[MarketDataDashboardInstrument] = []
    issues: list[MarketDataDashboardIssue] = []
    for batch in result.plan.batches:
        batch_result = by_index.get(batch.batch_index)
        if batch_result is None:
            raise ValueError("Scan result is missing a planned batch.")
        if batch_result.status is ScanBatchStatus.SKIPPED:
            for instrument in batch.instruments:
                instruments.append(MarketDataDashboardInstrument(instrument, "failed", None, None, ("PRIOR_BATCH_BLOCKED",)))
                issues.append(MarketDataDashboardIssue("PRIOR_BATCH_BLOCKED", instrument, "failed"))
            continue
        for feed in batch_result.feeds:
            item = _instrument_from_feed(feed)
            instruments.append(item)
            severity = "failed" if item.status == "failed" else "issue"
            issues.extend(MarketDataDashboardIssue(code, item.instrument, severity) for code in item.issue_codes)
    canonical_instruments = tuple(sorted(instruments, key=lambda item: item.instrument))
    canonical_issues = tuple(sorted(set(issues), key=lambda item: (item.instrument or "", item.severity, item.code)))
    summary = MarketDataDashboardSummary(
        result.status.value,
        len(canonical_instruments),
        sum(item.status == "completed" for item in canonical_instruments),
        sum(item.status == "failed" for item in canonical_instruments),
        sum(item.status == "issue" for item in canonical_instruments),
    )
    return MarketDataDashboardProjection(version, summary, result.plan.plan_hash, result.scan_hash, canonical_instruments, canonical_issues)


__all__ = [
    "MARKET_DATA_DASHBOARD_PROJECTION_VERSION",
    "MarketDataDashboardInstrument",
    "MarketDataDashboardIssue",
    "MarketDataDashboardProjection",
    "MarketDataDashboardSummary",
    "MarketDataDashboardVersion",
    "build_market_data_dashboard_projection",
]
