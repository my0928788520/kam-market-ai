"""Explicit Windows-local entry point for Sprint 9A live futures verification."""

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
from .futures_live_probe import (
    FubonFuturesContractDiscovery,
    FubonFuturesLiveProbe,
    FuturesContractDiscoveryError,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="KAM Sprint 9A 富邦期貨唯讀行情驗證")
    parser.add_argument(
        "--live",
        action="store_true",
        help="明確允許本次本機行情授權與連線",
    )
    parser.add_argument("--env", default=".env", help="本機 .env 路徑；內容永不輸出")
    parser.add_argument("--after-hours", action="store_true", help="驗證夜盤行情")
    parser.add_argument("--duration-seconds", type=float, default=30.0)
    parser.add_argument(
        "--verify-reconnect",
        action="store_true",
        help="完成後再連線並重新訂閱一次",
    )
    parser.add_argument("--stale-after-seconds", type=float, default=300.0)
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
        contracts = FubonFuturesContractDiscovery(result.clients).resolve(
            after_hours=args.after_hours
        )
    except FuturesContractDiscoveryError as error:
        print(json.dumps({"success": False, "failure_stage": str(error)}))
        return 1
    try:
        report = FubonFuturesLiveProbe(
            result.clients,
            stale_after_seconds=args.stale_after_seconds,
        ).run(
            contracts,
            duration_seconds=args.duration_seconds,
            verify_reconnect=args.verify_reconnect,
        )
    except (TypeError, ValueError):
        print(json.dumps({"success": False, "failure_stage": "PROBE_CONFIGURATION_ERROR"}))
        return 2
    print(json.dumps(report.safe_payload(), ensure_ascii=False))
    return 0 if report.success else 1


if __name__ == "__main__":
    raise SystemExit(main())
