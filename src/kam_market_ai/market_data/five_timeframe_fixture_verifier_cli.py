"""CLI for one deterministic, offline five-timeframe contract verification."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence

from .five_timeframe_fixture_verifier import FIXTURE_ID, run_controlled_fixture_verification


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="KAM 五週期受控假資料單次唯讀驗證")
    parser.add_argument("--fixture", choices=(FIXTURE_ID,), required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    build_parser().parse_args(argv)
    report = run_controlled_fixture_verification()
    print(json.dumps(report.payload, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
