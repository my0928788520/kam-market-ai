"""Explicit Windows-local CLI for one live TMF five-timeframe verification."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from datetime import date, datetime

from kam_market_ai.authorization.bootstrap import (
    AuthorizationBootstrap,
    AuthorizationFailure,
    AuthorizationSettings,
)
from kam_market_ai.config import Settings, UnsafeConfigurationError
from kam_market_ai.models import Instrument

from .five_timeframe_attestation_file import (
    load_verified_attestation,
    write_attestation_template,
)
from .fubon_five_timeframe_pipeline import FubonFiveTimeframeCandlePipeline
from .fubon_live_five_timeframe_verifier import (
    CandleClassification,
    FubonLiveFiveTimeframeVerifier,
)
from .fubon_neo import (
    FubonIntradayCandlesAdapter,
    IntradayCandleContractError,
    ResolvedFuturesContract,
    VerifiedContractResolver,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="KAM 富邦 TMF 真實五週期單次唯讀驗證")
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--env", default=".env")
    parser.add_argument("--symbol", required=True, help="已核實的富邦 TMF 契約代碼")
    parser.add_argument("--session", default=None, help="已核實的官方 session token")
    parser.add_argument("--after-hours", action="store_true")
    parser.add_argument(
        "--classify",
        action="append",
        default=[],
        metavar="START,TRADING_DATE,WEEK_START",
    )
    parser.add_argument("--complete-trading-date", action="append", default=[])
    parser.add_argument("--complete-week-start", action="append", default=[])
    parser.add_argument("--attestation-file", help="已人工核實的 JSON 認證檔")
    parser.add_argument("--write-attestation-template", help="將待核實認證草稿寫入此路徑")
    return parser


def _classification(value: str) -> CandleClassification:
    parts = value.split(",")
    if len(parts) != 3:
        raise ValueError("LIVE_VERIFIER_CLASSIFICATION_FORMAT_ERROR")
    return CandleClassification(
        datetime.fromisoformat(parts[0]),
        date.fromisoformat(parts[1]),
        date.fromisoformat(parts[2]),
    )


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
        if args.attestation_file and (
            args.classify or args.complete_trading_date or args.complete_week_start
        ):
            raise ValueError("ATTESTATION_FILE_CANNOT_BE_COMBINED_WITH_INLINE_VALUES")
        if args.attestation_file:
            attestation = load_verified_attestation(args.attestation_file)
            classifications = attestation.classifications
            complete_dates = attestation.complete_trading_dates
            complete_weeks = attestation.complete_week_starts
        else:
            classifications = tuple(_classification(value) for value in args.classify)
            complete_dates = tuple(date.fromisoformat(value) for value in args.complete_trading_date)
            complete_weeks = tuple(date.fromisoformat(value) for value in args.complete_week_start)
        Settings.load(args.env)
        result = (bootstrap or AuthorizationBootstrap()).run(
            AuthorizationSettings.from_local_env(args.env),
            dry_run=False,
        )
    except (AuthorizationFailure, UnsafeConfigurationError, ValueError):
        print(json.dumps({"success": False, "failure_stage": "INPUT_OR_AUTHORIZATION_ERROR"}))
        return 2
    if result.clients is None:
        print(json.dumps({"success": False, "failure_stage": "MARKET_CLIENTS_UNAVAILABLE"}))
        return 2
    resolver = VerifiedContractResolver((
        ResolvedFuturesContract(Instrument.TMF, args.symbol, args.after_hours),
    ))
    pipeline = FubonFiveTimeframeCandlePipeline(
        FubonIntradayCandlesAdapter(result.clients, resolver),
    )
    try:
        payload = FubonLiveFiveTimeframeVerifier(pipeline).run(
            symbol=args.symbol,
            session=args.session,
            after_hours=args.after_hours,
            classifications=classifications,
            complete_trading_dates=complete_dates,
            complete_week_starts=complete_weeks,
        )
    except (IntradayCandleContractError, TypeError, ValueError):
        print(json.dumps({"success": False, "failure_stage": "VERIFICATION_CONTRACT_ERROR"}))
        return 1
    except Exception:  # noqa: BLE001
        print(json.dumps({"success": False, "failure_stage": "CANDLE_ENDPOINT_ERROR"}))
        return 1
    if args.write_attestation_template:
        try:
            target = write_attestation_template(args.write_attestation_template, payload)
        except (OSError, TypeError, ValueError):
            print(json.dumps({"success": False, "failure_stage": "ATTESTATION_TEMPLATE_ERROR"}))
            return 1
        payload["attestation_template_written"] = str(target)
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return 0 if payload["success"] else 3


if __name__ == "__main__":
    raise SystemExit(main())
