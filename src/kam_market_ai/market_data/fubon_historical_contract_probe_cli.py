"""Windows-local CLI for a non-invoking Fubon historical API fingerprint."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence

from ..authorization.bootstrap import (
    AuthorizationBootstrap,
    AuthorizationFailure,
    AuthorizationSettings,
)
from ..config import Settings, UnsafeConfigurationError
from .fubon_historical_contract_probe import (
    HistoricalContractProbeError,
    probe_fubon_historical_contract,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="KAM 富邦期貨歷史行情唯讀契約探測")
    parser.add_argument(
        "--live",
        action="store_true",
        help="明確允許本機登入並初始化行情 client；不呼叫行情 endpoint",
    )
    parser.add_argument("--env", default=".env", help="本機 .env 路徑；內容永不輸出")
    return parser


def main(
    argv: Sequence[str] | None = None,
    *,
    bootstrap: AuthorizationBootstrap | None = None,
) -> int:
    args = build_parser().parse_args(argv)
    if not args.live:
        print(json.dumps({"success": False, "failure_stage": "LIVE_FLAG_REQUIRED"}))
        return 2
    try:
        Settings.load(args.env)
        result = (bootstrap or AuthorizationBootstrap()).run(
            AuthorizationSettings.from_local_env(args.env),
            dry_run=False,
        )
    except (AuthorizationFailure, UnsafeConfigurationError) as error:
        stage = getattr(getattr(error, "stage", None), "value", "UNSAFE_CONFIGURATION")
        print(json.dumps({"success": False, "failure_stage": stage}))
        return 2
    if result.clients is None:
        print(json.dumps({"success": False, "failure_stage": "MARKET_CLIENTS_UNAVAILABLE"}))
        return 2
    try:
        fingerprint = probe_fubon_historical_contract(result.clients)
    except HistoricalContractProbeError as error:
        print(json.dumps({"success": False, "failure_stage": str(error)}))
        return 1
    print(json.dumps({"success": True, **fingerprint.safe_payload()}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
