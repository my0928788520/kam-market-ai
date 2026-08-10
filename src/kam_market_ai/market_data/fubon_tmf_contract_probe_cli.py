"""Explicit Windows-local entry point for one Fubon TMF ticker-list request."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence

from kam_market_ai.authorization.bootstrap import (
    AuthorizationBootstrap,
    AuthorizationFailure,
    AuthorizationSettings,
)
from kam_market_ai.config import Settings, UnsafeConfigurationError

from .fubon_tmf_contract_probe import FubonTmfContractProbe, FubonTmfContractProbeError


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="KAM 富邦微型臺指契約代碼單次唯讀探測")
    parser.add_argument("--live", action="store_true", help="明確允許本次本機行情授權與單次請求")
    parser.add_argument("--env", default=".env", help="本機 .env 路徑；內容永不輸出")
    parser.add_argument("--after-hours", action="store_true", help="查詢夜盤商品清單")
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
        report = FubonTmfContractProbe(result.clients).run(after_hours=args.after_hours)
    except FubonTmfContractProbeError as error:
        print(json.dumps({"success": False, "failure_stage": str(error)}))
        return 1
    except (TypeError, ValueError):
        print(json.dumps({"success": False, "failure_stage": "TICKERS_CONTRACT_ERROR"}))
        return 1
    # Provider exceptions may contain request internals; never print them.
    except Exception:  # noqa: BLE001
        print(json.dumps({"success": False, "failure_stage": "TICKERS_ENDPOINT_ERROR"}))
        return 1
    print(json.dumps(report.safe_payload(), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
