"""Start only the local read-only Paper Trading operator display."""
from __future__ import annotations

from wsgiref.simple_server import make_server
import argparse

from kam_market_ai.paper_trading.operator_app import create_operator_app
from kam_market_ai.paper_trading.operator_presenter import PaperTradingOperatorView


def _empty_view() -> PaperTradingOperatorView:
    return PaperTradingOperatorView("KAM 模擬交易操作台", "尚未載入模擬委託建議。本機頁面目前為唯讀模式。", {"status": "尚無委託建議"}, {"state": "尚無結果"}, {"cash": "—"}, (), False)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="本機唯讀 KAM 模擬交易操作台")
    parser.add_argument("--demo", action="store_true", help="載入明確標示的離線示範資料")
    parser.add_argument("--kam-rule-demo", action="store_true", help="載入 KAM 規則離線示範資料")
    args = parser.parse_args()
    app = create_operator_app(_empty_view)
    if args.demo:
        from kam_market_ai.paper_trading.operator_app import create_demo_operator_app
        app = create_demo_operator_app()
    if args.kam_rule_demo:
        from kam_market_ai.paper_trading.operator_app import create_kam_rule_demo_operator_app
        app = create_kam_rule_demo_operator_app()
    with make_server("127.0.0.1", 8000, app) as server:
        print("KAM 模擬交易操作台：http://127.0.0.1:8000/")
        server.serve_forever()
