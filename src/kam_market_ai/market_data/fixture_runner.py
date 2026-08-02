"""Explicit-path fixture runner and deterministic Offline Research export."""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from hashlib import sha256
from json import dumps, loads
from pathlib import Path
from typing import Sequence

from .pipeline_cli import OFFLINE_RESEARCH_PIPELINE_CLI_VERSION, build_offline_pipeline_output, build_parser


OFFLINE_RESEARCH_FIXTURE_EXPORT_VERSION = "1.1.0"


def _hash(payload: object) -> str:
    return sha256(dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class OfflineResearchExportMetadata:
    export_version: str
    cli_version: str
    source: str
    provider_id: str
    dataset_id: str
    dataset_version: str
    pipeline_hash: str
    projection_hash: str

    def __post_init__(self) -> None:
        if self.export_version != OFFLINE_RESEARCH_FIXTURE_EXPORT_VERSION:
            raise ValueError("Unsupported fixture export version.")
        if self.cli_version != OFFLINE_RESEARCH_PIPELINE_CLI_VERSION:
            raise ValueError("Unsupported pipeline CLI version.")
        if not all((self.source, self.provider_id, self.dataset_id, self.dataset_version, self.pipeline_hash, self.projection_hash)):
            raise ValueError("Fixture export metadata is incomplete.")

    def canonical_payload(self) -> dict[str, str]:
        return {
            "export_version": self.export_version,
            "cli_version": self.cli_version,
            "source": self.source,
            "provider_id": self.provider_id,
            "dataset_id": self.dataset_id,
            "dataset_version": self.dataset_version,
            "pipeline_hash": self.pipeline_hash,
            "projection_hash": self.projection_hash,
        }


@dataclass(frozen=True, slots=True)
class OfflineResearchFixtureExport:
    metadata: OfflineResearchExportMetadata
    pipeline_payload: dict[str, object]

    def canonical_payload(self) -> dict[str, object]:
        return {"metadata": self.metadata.canonical_payload(), "pipeline": self.pipeline_payload}

    @property
    def export_hash(self) -> str:
        return _hash(self.canonical_payload())

    def serialize(self) -> str:
        payload = {**self.canonical_payload(), "export_hash": self.export_hash}
        return dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def build_fixture_export(args: argparse.Namespace) -> OfflineResearchFixtureExport:
    """Build an export from the existing offline CLI without writing anything."""
    pipeline_payload = loads(build_offline_pipeline_output(args))
    metadata = OfflineResearchExportMetadata(
        OFFLINE_RESEARCH_FIXTURE_EXPORT_VERSION,
        pipeline_payload["cli_version"],
        args.source,
        args.provider_id,
        args.dataset_id,
        args.dataset_version,
        pipeline_payload["pipeline_hash"],
        pipeline_payload["projection_hash"],
    )
    return OfflineResearchFixtureExport(metadata, pipeline_payload)


def write_fixture_export(
    args: argparse.Namespace,
    output_path: Path,
    *,
    overwrite_policy: str = "forbid",
) -> OfflineResearchFixtureExport:
    """Write one deterministic export to one explicit, new local JSON path."""
    if not isinstance(output_path, Path) or not output_path.is_absolute():
        raise ValueError("Output path must be explicit and absolute.")
    if output_path.suffix.lower() != ".json":
        raise ValueError("Output path must use the .json extension.")
    if not output_path.parent.is_dir():
        raise ValueError("Output directory must already exist.")
    if overwrite_policy not in {"forbid", "replace"}:
        raise ValueError("Unknown overwrite policy.")
    if output_path.exists() and overwrite_policy == "forbid":
        raise ValueError("Refusing to overwrite an existing export.")
    export = build_fixture_export(args)
    output_path.write_text(export.serialize(), encoding="utf-8")
    return export


def build_export_parser() -> argparse.ArgumentParser:
    parser = build_parser()
    parser.description = "Run offline research and write one deterministic JSON export."
    next(action for action in parser._actions if action.dest == "output").required = True
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_export_parser().parse_args(argv)
    try:
        export = write_fixture_export(args, args.output, overwrite_policy=args.overwrite)
        print(export.serialize())
    except (OSError, ValueError, KeyError) as error:
        code = "INPUT_UNAVAILABLE" if isinstance(error, OSError) else "VALIDATION_FAILED"
        print(dumps({"export_version": OFFLINE_RESEARCH_FIXTURE_EXPORT_VERSION, "error_code": code, "status": "blocked"}, sort_keys=True, separators=(",", ":"), ensure_ascii=True))
        return 2
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
