"""Local, read-only live five-timeframe dashboard service."""

from __future__ import annotations

import argparse
import json
import threading
from collections.abc import Sequence
from pathlib import Path
from time import monotonic
from wsgiref.simple_server import make_server

from kam_market_ai.authorization.bootstrap import (
    AuthorizationBootstrap,
    AuthorizationFailure,
    AuthorizationSettings,
)
from kam_market_ai.config import Settings, UnsafeConfigurationError
from kam_market_ai.dashboard.app import DashboardApp
from kam_market_ai.live_read_only.five_timeframe_snapshot import write_five_timeframe_snapshot
from kam_market_ai.models import Instrument

from .fubon_five_timeframe_pipeline import FubonFiveTimeframeCandlePipeline
from .fubon_live_five_timeframe_verifier import FubonLiveFiveTimeframeVerifier
from .fubon_neo import (
    FubonIntradayCandlesAdapter,
    ResolvedFuturesContract,
    VerifiedContractResolver,
)


class LiveFiveTimeframeSnapshotRefresher:
    def __init__(
        self,
        verifier: FubonLiveFiveTimeframeVerifier,
        *,
        symbol: str,
        session: str | None,
        after_hours: bool,
        snapshot_path: str | Path,
    ) -> None:
        if not isinstance(verifier, FubonLiveFiveTimeframeVerifier):
            raise TypeError("FubonLiveFiveTimeframeVerifier is required")
        self.verifier = verifier
        self.symbol = symbol
        self.session = session
        self.after_hours = after_hours
        self.snapshot_path = Path(snapshot_path)

    def refresh_once(self) -> dict[str, object]:
        payload = self.verifier.run(
            symbol=self.symbol,
            session=self.session,
            after_hours=self.after_hours,
        )
        write_five_timeframe_snapshot(self.snapshot_path, payload)
        return payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="KAM 富邦 TMF 本機五週期唯讀儀表板")
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--env", default=".env")
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--session", default=None)
    parser.add_argument("--after-hours", action="store_true")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--refresh-seconds", type=int, default=60)
    parser.add_argument("--snapshot", default="debug/five_timeframe/live.json")
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
    if args.host not in {"127.0.0.1", "localhost"} or args.port <= 0 or args.refresh_seconds < 15:
        print(json.dumps({"success": False, "failure_stage": "LOCAL_SERVICE_INPUT_ERROR"}))
        return 2
    try:
        Settings.load(args.env)
        result = (bootstrap or AuthorizationBootstrap()).run(
            AuthorizationSettings.from_local_env(args.env),
            dry_run=False,
        )
    except (AuthorizationFailure, UnsafeConfigurationError, ValueError):
        print(json.dumps({"success": False, "failure_stage": "AUTHORIZATION_ERROR"}))
        return 2
    if result.clients is None:
        print(json.dumps({"success": False, "failure_stage": "MARKET_CLIENTS_UNAVAILABLE"}))
        return 2

    resolver = VerifiedContractResolver((
        ResolvedFuturesContract(Instrument.TMF, args.symbol, args.after_hours),
    ))
    verifier = FubonLiveFiveTimeframeVerifier(FubonFiveTimeframeCandlePipeline(
        FubonIntradayCandlesAdapter(result.clients, resolver),
    ))
    refresher = LiveFiveTimeframeSnapshotRefresher(
        verifier,
        symbol=args.symbol,
        session=args.session,
        after_hours=args.after_hours,
        snapshot_path=args.snapshot,
    )
    try:
        refresher.refresh_once()
    except Exception:  # noqa: BLE001
        print(json.dumps({"success": False, "failure_stage": "INITIAL_REFRESH_ERROR"}))
        return 1

    stop = threading.Event()

    def refresh_loop() -> None:
        deadline = monotonic() + args.refresh_seconds
        while not stop.wait(max(0.0, deadline - monotonic())):
            try:
                refresher.refresh_once()
            except Exception:  # noqa: BLE001
                pass
            deadline += args.refresh_seconds

    worker = threading.Thread(target=refresh_loop, name="kam-five-timeframe-refresh", daemon=True)
    worker.start()
    print(json.dumps({
        "success": True,
        "mode": "local_read_only_five_timeframe_dashboard",
        "url": f"http://{args.host}:{args.port}/api/five-timeframe",
        "refresh_seconds": args.refresh_seconds,
        "trading_enabled": False,
        "live_order_allowed": False,
    }, ensure_ascii=False))
    try:
        with make_server(
            args.host,
            args.port,
            DashboardApp(five_timeframe_snapshot_path=args.snapshot),
        ) as server:
            server.serve_forever()
    except KeyboardInterrupt:
        return 0
    finally:
        stop.set()
        worker.join(timeout=1)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["LiveFiveTimeframeSnapshotRefresher", "build_parser", "main"]
