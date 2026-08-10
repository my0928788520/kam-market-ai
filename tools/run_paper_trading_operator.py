"""Start only the local read-only Paper Trading operator display."""

from __future__ import annotations

import argparse
import json
import os
from wsgiref.simple_server import make_server

from kam_market_ai.authorization.bootstrap import (
    AuthorizationBootstrap,
    AuthorizationFailure,
    AuthorizationSettings,
)
from kam_market_ai.config import Settings, UnsafeConfigurationError
from kam_market_ai.live_read_only.providers.fubon_futures_runtime import (
    FubonFuturesLiveClient,
    FubonFuturesRuntimeError,
)
from kam_market_ai.live_read_only.runtime_market_source import RuntimeMarketSourceError
from kam_market_ai.market_data.futures_live_probe import (
    FubonFuturesContractDiscovery,
    FuturesContractDiscoveryError,
)
from kam_market_ai.paper_trading.operator_app import create_operator_app
from kam_market_ai.paper_trading.operator_presenter import PaperTradingOperatorView


def _empty_view() -> PaperTradingOperatorView:
    return PaperTradingOperatorView(
        "KAM 交易決策操作台",
        "尚未載入模擬委託建議。本機頁面目前為唯讀模式。",
        {"status": "尚無委託建議"},
        {"state": "尚無結果"},
        {"cash": "—"},
        (),
        False,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="本機唯讀 KAM 交易決策操作台")
    parser.add_argument("--demo", action="store_true", help="載入明確標示的離線示範資料")
    parser.add_argument("--kam-rule-demo", action="store_true", help="載入 KAM 規則離線示範資料")
    parser.add_argument(
        "--market-source",
        choices=("offline-demo", "fake-live", "fugle-live", "fubon-live"),
        default="offline-demo",
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="明確允許本次本機富邦行情授權與連線",
    )
    parser.add_argument("--env", default=".env", help="本機 .env 路徑；內容永不輸出")
    parser.add_argument("--after-hours", action="store_true", help="使用富邦期貨夜盤行情")
    parser.add_argument(
        "--chart-history-json",
        help="唯讀載入明確匯出的歷史 OHLCV JSON；不連線券商或網路",
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8000")))
    return parser


def build_operator_application(
    args: argparse.Namespace,
    *,
    bootstrap: AuthorizationBootstrap | None = None,
):
    """Compose a read-only app without starting a server or opening a socket."""
    from kam_market_ai.live_read_only.runtime_market_source import (
        RuntimeMarketSourceConfig,
        RuntimeMarketSourceMode,
        RuntimeMarketSourceSelector,
    )

    mode = RuntimeMarketSourceMode(args.market_source)
    live_client = None
    if mode is RuntimeMarketSourceMode.FUBON_LIVE:
        if not args.live:
            raise RuntimeMarketSourceError("LIVE_FLAG_REQUIRED")
        Settings.load(args.env)
        result = (bootstrap or AuthorizationBootstrap()).run(
            AuthorizationSettings.from_local_env(args.env),
            dry_run=False,
        )
        if result.clients is None:
            raise RuntimeMarketSourceError("MARKET_CLIENTS_UNAVAILABLE")
        contracts = FubonFuturesContractDiscovery(result.clients).resolve(
            after_hours=args.after_hours
        )
        live_client = FubonFuturesLiveClient(result.clients, contracts)
        live_client.start()
    selection = RuntimeMarketSourceSelector().select(
        RuntimeMarketSourceConfig(mode),
        fubon_live_client=live_client,
    )
    market_data_source = selection.provider
    chart_data_source = None
    if args.chart_history_json:
        from kam_market_ai.paper_trading.historical_chart_source import load_exported_historical_chart_source
        chart_data_source = load_exported_historical_chart_source(args.chart_history_json)
    app_options = {"market_data_source": market_data_source}
    if chart_data_source is not None:
        app_options["chart_data_source"] = chart_data_source
    app = create_operator_app(_empty_view, **app_options)
    if args.demo:
        from kam_market_ai.paper_trading.operator_app import create_demo_operator_app

        app = create_demo_operator_app(**app_options)
    if args.kam_rule_demo:
        from kam_market_ai.paper_trading.operator_app import create_kam_rule_demo_operator_app

        app = create_kam_rule_demo_operator_app(**app_options)
    close = getattr(market_data_source, "close", None)
    if callable(close):
        app.close_market_data = close  # type: ignore[attr-defined]
    return app


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        app = build_operator_application(args)
    except (
        AuthorizationFailure,
        FuturesContractDiscoveryError,
        FubonFuturesRuntimeError,
        RuntimeMarketSourceError,
        UnsafeConfigurationError,
    ) as error:
        stage = getattr(getattr(error, "stage", None), "value", str(error))
        print(json.dumps({"success": False, "failure_stage": stage}))
        return 2
    try:
        with make_server(args.host, args.port, app) as server:
            print(f"KAM 唯讀操作台：http://{args.host}:{args.port}/")
            server.serve_forever()
    finally:
        close = getattr(app, "close_market_data", None)
        if callable(close):
            close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
