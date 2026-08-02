"""Run the root KAM Dashboard locally; this never calls the broker SDK."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from wsgiref.simple_server import make_server


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from kam_market_ai.dashboard.app import DashboardApp


def main() -> int:
    parser = argparse.ArgumentParser(description="Run local KAM Dashboard")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--snapshot", default="debug/position/dashboard_position_snapshot.json")
    args = parser.parse_args()
    with make_server(args.host, args.port, DashboardApp(args.snapshot)) as server:
        print(f"Dashboard: http://{args.host}:{args.port}/")
        server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
