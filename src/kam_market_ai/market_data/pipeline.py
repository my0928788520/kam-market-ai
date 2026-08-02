"""Frozen, offline-only Research v1 pipeline entrypoint."""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from json import dumps

from .dashboard_projection import (
    MARKET_DATA_DASHBOARD_PROJECTION_VERSION,
    MarketDataDashboardProjection,
    build_market_data_dashboard_projection,
)
from .historical_feed import HISTORICAL_FEED_VERSION, OfflineHistoricalDataset
from .provider_adapter import MARKET_DATA_PROVIDER_ADAPTER_VERSION
from .provider_contract import MARKET_DATA_PROVIDER_CONTRACT_VERSION, MarketDataProviderContract
from .scan_engine import (
    MARKET_DATA_SCAN_ENGINE_VERSION,
    MarketDataScanPlan,
    MarketDataScanResult,
    ScanExecutionStatus,
    ScanPlanStatus,
    execute_market_data_scan,
)
from .scan_result import MARKET_DATA_SCAN_RESULT_MODEL_VERSION


OFFLINE_RESEARCH_PIPELINE_VERSION = "1.0"


def _hash(payload: object) -> str:
    return sha256(dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class OfflineResearchPipelineVersion:
    pipeline_version: str = OFFLINE_RESEARCH_PIPELINE_VERSION
    provider_contract_version: str = MARKET_DATA_PROVIDER_CONTRACT_VERSION
    provider_adapter_version: str = MARKET_DATA_PROVIDER_ADAPTER_VERSION
    historical_feed_version: str = HISTORICAL_FEED_VERSION
    scan_engine_version: str = MARKET_DATA_SCAN_ENGINE_VERSION
    scan_result_model_version: str = MARKET_DATA_SCAN_RESULT_MODEL_VERSION
    dashboard_projection_version: str = MARKET_DATA_DASHBOARD_PROJECTION_VERSION

    def __post_init__(self) -> None:
        expected = (
            OFFLINE_RESEARCH_PIPELINE_VERSION,
            MARKET_DATA_PROVIDER_CONTRACT_VERSION,
            MARKET_DATA_PROVIDER_ADAPTER_VERSION,
            HISTORICAL_FEED_VERSION,
            MARKET_DATA_SCAN_ENGINE_VERSION,
            MARKET_DATA_SCAN_RESULT_MODEL_VERSION,
            MARKET_DATA_DASHBOARD_PROJECTION_VERSION,
        )
        actual = (
            self.pipeline_version,
            self.provider_contract_version,
            self.provider_adapter_version,
            self.historical_feed_version,
            self.scan_engine_version,
            self.scan_result_model_version,
            self.dashboard_projection_version,
        )
        if actual != expected:
            raise ValueError("Unsupported Offline Research pipeline version matrix.")


@dataclass(frozen=True, slots=True)
class OfflineResearchPipelineResult:
    version: OfflineResearchPipelineVersion
    scan_result: MarketDataScanResult
    dashboard_projection: MarketDataDashboardProjection

    def canonical_payload(self) -> dict[str, object]:
        return {
            "pipeline_version": self.version.pipeline_version,
            "version_matrix": {
                "provider_contract": self.version.provider_contract_version,
                "provider_adapter": self.version.provider_adapter_version,
                "historical_feed": self.version.historical_feed_version,
                "scan_engine": self.version.scan_engine_version,
                "scan_result_model": self.version.scan_result_model_version,
                "dashboard_projection": self.version.dashboard_projection_version,
            },
            "plan_hash": self.scan_result.plan.plan_hash,
            "scan_hash": self.scan_result.scan_hash,
            "scan_status": self.scan_result.status.value,
            "projection_hash": self.dashboard_projection.projection_hash,
            "projection_status": self.dashboard_projection.summary.overall_status,
            "product_scope": "MARKET_RESEARCH_ONLY",
            "network_enabled": False,
            "live_provider_enabled": False,
        }

    @property
    def pipeline_hash(self) -> str:
        return _hash(self.canonical_payload())

    def serialize(self) -> str:
        return dumps(self.canonical_payload(), sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _validate_inputs(
    provider: MarketDataProviderContract,
    dataset: OfflineHistoricalDataset,
    scan_plan: MarketDataScanPlan,
) -> None:
    if not isinstance(provider, MarketDataProviderContract):
        raise ValueError("Unsupported provider contract type.")
    if not isinstance(dataset, OfflineHistoricalDataset):
        raise ValueError("Unsupported offline dataset type.")
    if not isinstance(scan_plan, MarketDataScanPlan):
        raise ValueError("Unsupported scan plan type.")
    if scan_plan.status is not ScanPlanStatus.READY:
        raise ValueError("Blocked scan plans cannot enter the offline pipeline.")
    if scan_plan.request.provider != provider or scan_plan.request.dataset != dataset:
        raise ValueError("Pipeline provider and dataset must match scan plan lineage.")
    if provider.research_only is not True or provider.network_enabled is not False or provider.live_provider_enabled is not False:
        raise ValueError("Offline pipeline requires a research-only offline provider.")


def _validate_output(result: MarketDataScanResult, projection: MarketDataDashboardProjection) -> None:
    if result.status.value != projection.summary.overall_status:
        raise ValueError("Pipeline scan/projection status mismatch.")
    if result.status is ScanExecutionStatus.COMPLETED and (
        projection.summary.failed_instrument_count != 0 or projection.summary.issue_instrument_count != 0
    ):
        raise ValueError("Partial scan success cannot be marked completed.")
    if result.status is ScanExecutionStatus.COMPLETED_WITH_ISSUES and projection.summary.issue_instrument_count == 0:
        raise ValueError("Partial scan success requires projection issues.")
    if result.status is ScanExecutionStatus.BLOCKED and projection.summary.failed_instrument_count == 0:
        raise ValueError("Blocked scan requires failed projection instruments.")


def run_offline_research_pipeline(
    provider: MarketDataProviderContract,
    dataset: OfflineHistoricalDataset,
    scan_plan: MarketDataScanPlan,
    *,
    version: OfflineResearchPipelineVersion | None = None,
) -> OfflineResearchPipelineResult:
    """Run the frozen offline pipeline over an existing, ready scan plan."""
    pipeline_version = version or OfflineResearchPipelineVersion()
    _validate_inputs(provider, dataset, scan_plan)
    scan_result = execute_market_data_scan(scan_plan)
    projection = build_market_data_dashboard_projection(
        scan_result,
        scan_engine_version=pipeline_version.scan_engine_version,
        projection_version=pipeline_version.dashboard_projection_version,
    )
    _validate_output(scan_result, projection)
    return OfflineResearchPipelineResult(pipeline_version, scan_result, projection)


__all__ = [
    "OFFLINE_RESEARCH_PIPELINE_VERSION",
    "OfflineResearchPipelineResult",
    "OfflineResearchPipelineVersion",
    "run_offline_research_pipeline",
]
