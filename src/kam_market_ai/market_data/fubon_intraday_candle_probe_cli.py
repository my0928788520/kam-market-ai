"""Explicit Windows-local entry point for one Fubon candle request."""

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
from kam_market_ai.models import Instrument

from .fubon_intraday_candle_probe import FubonIntradayCandleProbe
from .fubon_neo import IntradayCandleContractError


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="KAM 富邦單次期權日內 K 線唯讀驗證")
    parser.add_argument("--live", action="store_true", help="明確允許本次本機行情授權與單次請求")
    parser.add_argument("--env", default=".env", help="本機 .env 路徑；內容永不輸出")
    parser.add_argument("--instrument", choices=("TX", "MTX"), required=True)
    parser.add_argument("--symbol", required=True, help="已核實的富邦期貨商品代碼")
    parser.add_argument("--session", required=True, help="已由官方文件核實的 session token")
    parser.add_argument("--timeframe", required=True, help="已由官方文件核實的 timeframe token")
    parser.add_argument("--interval-minutes", type=int, required=True)
    parser.add_argument("--after-hours", action="store_true")
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
        report = FubonIntradayCandleProbe(result.clients).run(
            instrument=Instrument(args.instrument),
            symbol=args.symbol,
            session=args.session,
            timeframe=args.timeframe,
            interval_minutes=args.interval_minutes,
            after_hours=args.after_hours,
        )
    except (IntradayCandleContractError, TypeError, ValueError):
        print(json.dumps({"success": False, "failure_stage": "CANDLE_CONTRACT_ERROR"}))
        return 1
    # Provider exceptions can include request internals. Collapse every such
    # failure to one stable stage instead of printing the original exception.
    except Exception:  # noqa: BLE001
        print(json.dumps({"success": False, "failure_stage": "CANDLE_ENDPOINT_ERROR"}))
        return 1
    print(json.dumps(report.safe_payload(), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
