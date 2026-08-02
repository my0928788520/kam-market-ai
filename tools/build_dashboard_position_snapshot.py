"""Create a Dashboard position snapshot from existing de-identified parser artifacts."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def build_snapshot(normalized: dict[str, Any], matched: dict[str, Any], *, query_success: bool) -> dict[str, Any]:
    updated_at = datetime.now(UTC).isoformat()
    report = matched.get("matched", {})
    positions = report.get("positions", [])
    if not query_success:
        return {"query_success": False, "matched_rows": 0, "updated_at": updated_at, "status": "SYNC_ERROR", "error_code": "QUERY_FAILED"}
    if not positions:
        return {"query_success": True, "matched_rows": 0, "updated_at": updated_at, "status": str(report.get("status", "EMPTY"))}
    match = positions[0]
    source_indexes = set(match.get("source_indexes", []))
    row = next((item for item in normalized.get("positions", []) if item.get("source_index") in source_indexes), None)
    if not isinstance(row, dict):
        return {"query_success": False, "matched_rows": 0, "updated_at": updated_at, "status": "SYNC_ERROR", "error_code": "MATCHED_ROW_MISSING"}
    return {
        "query_success": True, "matched_rows": len(positions), "product_code": row.get("product_code"),
        "symbol_raw": row.get("symbol_raw"), "expiry": row.get("contract_month"), "side": row.get("side"),
        "quantity": row.get("quantity"), "average_price": row.get("average_price"),
        "market_price": row.get("current_price"), "unrealized_pnl": row.get("unrealized_pnl"),
        "updated_at": updated_at, "status": report.get("status"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build de-identified Dashboard position snapshot")
    parser.add_argument("--normalized", default="debug/position/normalized_position.json")
    parser.add_argument("--matched", default="debug/position/matched_position.json")
    parser.add_argument("--output", default="debug/position/dashboard_position_snapshot.json")
    parser.add_argument("--query-success", action="store_true", help="Explicitly attest that the source capture query succeeded")
    args = parser.parse_args()
    normalized = json.loads(Path(args.normalized).read_text(encoding="utf-8"))
    matched = json.loads(Path(args.matched).read_text(encoding="utf-8"))
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(build_snapshot(normalized, matched, query_success=args.query_success), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
