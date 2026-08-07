"""Start only the local read-only Paper Trading operator display."""
from __future__ import annotations

from wsgiref.simple_server import make_server
import argparse
import os

from kam_market_ai.paper_trading.operator_app import create_operator_app
from kam_market_ai.paper_trading.operator_presenter import PaperTradingOperatorView


def _empty_view() -> PaperTradingOperatorView:
    return PaperTradingOperatorView("KAM 模擬交易操作台", "尚未載入模擬委託建議。本機頁面目前為唯讀模式。", {"status": "尚無委託建議"}, {"state": "尚無結果"}, {"cash": "—"}, (), False)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="本機唯讀 KAM 模擬交易操作台")
    parser.add_argument("--demo", action="store_true", help="載入明確標示的離線示範資料")
    parser.add_argument("--kam-rule-demo", action="store_true", help="載入 KAM 規則離線示範資料")
    parser.add_argument(
        "--market-source",
        choices=("offline-demo", "fake-live", "fugle-live"),
        default="offline-demo",
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8000")))
    return parser


def build_operator_application(args: argparse.Namespace):
    """Compose a read-only app without starting a server or opening a socket."""
    from kam_market_ai.live_read_only.runtime_market_source import (
        RuntimeMarketSourceConfig,
        RuntimeMarketSourceMode,
        RuntimeMarketSourceSelector,
    )
    market_data_source = RuntimeMarketSourceSelector().select(
        RuntimeMarketSourceConfig(RuntimeMarketSourceMode(args.market_source))
    ).provider
    app = create_operator_app(_empty_view, market_data_source=market_data_source)
    if args.demo:
        from kam_market_ai.paper_trading.operator_app import create_demo_operator_app
        app = create_demo_operator_app(market_data_source=market_data_source)
    if args.kam_rule_demo:
        from kam_market_ai.paper_trading.operator_app import create_kam_rule_demo_operator_app
        app = create_kam_rule_demo_operator_app(market_data_source=market_data_source)
    return app


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    app = build_operator_application(args)
    with make_server(args.host, args.port, app) as server:
        print("KAM 模擬交易操作台：http://127.0.0.1:8000/")
        server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
