"""Command-line entrypoint for the frozen, offline Research v1 pipeline."""
from __future__ import annotations

import argparse
from datetime import datetime
from json import dumps, loads
from pathlib import Path
from typing import Sequence

from .historical_feed import OfflineHistoricalDataset
from .pipeline import run_offline_research_pipeline
from .provider_adapter import OfflineMarketDataSource, OfflineMarketDataSourceKind
from .provider_contract import MarketDataProviderContract, MarketDataTimeframe, ResearchSourceKind
from .scan_engine import MarketDataScanRequest, build_market_data_scan_plan


OFFLINE_RESEARCH_PIPELINE_CLI_VERSION = "1.1.0-phase1"


def _parse_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _source_content(path: Path, kind: OfflineMarketDataSourceKind):
    content = path.read_text(encoding="utf-8")
    if kind in {OfflineMarketDataSourceKind.REPLAY, OfflineMarketDataSourceKind.FIXTURE}:
        decoded = loads(content)
        if not isinstance(decoded, list):
            raise ValueError("Replay and fixture input must contain a JSON array.")
        return tuple(decoded)
    return content


def _provider_source_kind(kind: OfflineMarketDataSourceKind) -> ResearchSourceKind:
    return ResearchSourceKind.REPLAY if kind is OfflineMarketDataSourceKind.REPLAY else ResearchSourceKind.FIXTURE


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the offline market-data research pipeline.")
    parser.add_argument("--source", required=True, choices=[item.value for item in OfflineMarketDataSourceKind])
    parser.add_argument("--input", required=True, type=Path, help="Explicit local offline dataset path.")
    parser.add_argument("--provider-id", required=True)
    parser.add_argument("--provider-version", default="1.0")
    parser.add_argument("--dataset-id", required=True)
    parser.add_argument("--dataset-version", default="1.0")
    parser.add_argument("--instruments", required=True, help="Comma-separated instruments.")
    parser.add_argument("--timeframe", required=True, choices=[item.value for item in MarketDataTimeframe])
    parser.add_argument("--start-at", required=True)
    parser.add_argument("--end-at", required=True)
    parser.add_argument("--as-of", required=True)
    parser.add_argument("--captured-at", required=True)
    parser.add_argument("--batch-size", type=int, default=100)
    return parser


def build_offline_pipeline_output(args: argparse.Namespace) -> str:
    """Load one explicit local dataset, run the offline pipeline, return compact JSON."""
    source_kind = OfflineMarketDataSourceKind(args.source)
    source = OfflineMarketDataSource(source_kind, _source_content(args.input, source_kind))
    provider = MarketDataProviderContract(
        args.provider_id,
        args.provider_version,
        _provider_source_kind(source_kind),
        (MarketDataTimeframe(args.timeframe),),
    )
    dataset = OfflineHistoricalDataset(
        args.dataset_id,
        args.dataset_version,
        _parse_timestamp(args.captured_at),
        source,
    )
    request = MarketDataScanRequest(
        provider,
        dataset,
        tuple(item.strip() for item in args.instruments.split(",")),
        MarketDataTimeframe(args.timeframe),
        _parse_timestamp(args.start_at),
        _parse_timestamp(args.end_at),
        _parse_timestamp(args.as_of),
        args.batch_size,
    )
    plan = build_market_data_scan_plan(request)
    result = run_offline_research_pipeline(provider, dataset, plan)
    payload = {
        "cli_version": OFFLINE_RESEARCH_PIPELINE_CLI_VERSION,
        "pipeline": result.canonical_payload(),
        "pipeline_hash": result.pipeline_hash,
        "dashboard_projection": result.dashboard_projection.canonical_payload(),
        "projection_hash": result.dashboard_projection.projection_hash,
    }
    return dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        print(build_offline_pipeline_output(args))
    except (OSError, ValueError) as error:
        print(dumps({"status": "blocked", "error": str(error)}, sort_keys=True, separators=(",", ":"), ensure_ascii=True))
        return 2
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
