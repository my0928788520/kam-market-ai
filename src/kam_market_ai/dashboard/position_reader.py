"""Fail-closed reader for the de-identified Dashboard position snapshot."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Mapping


DEFAULT_SNAPSHOT_PATH = Path("debug/position/dashboard_position_snapshot.json")
_REQUIRED_POSITION_FIELDS = ("product_code", "symbol_raw", "expiry", "side", "quantity", "average_price", "market_price", "unrealized_pnl", "updated_at", "status")


def sync_error(reason: str) -> dict[str, object]:
    return {
        "query_success": False,
        "matched_rows": 0,
        "product_code": None,
        "symbol_raw": None,
        "expiry": None,
        "side": None,
        "quantity": None,
        "average_price": None,
        "market_price": None,
        "unrealized_pnl": None,
        "updated_at": None,
        "status": "SYNC_ERROR",
        "display_state": "SYNC_ERROR",
        "error_code": reason,
    }


def _position(value: Mapping[str, Any]) -> dict[str, object]:
    query_success = value.get("query_success")
    matched_rows = value.get("matched_rows")
    if not isinstance(query_success, bool) or not isinstance(matched_rows, int) or matched_rows < 0:
        return sync_error("SNAPSHOT_SCHEMA_INVALID")
    if not query_success:
        return sync_error(str(value.get("error_code") or "QUERY_FAILED"))
    if matched_rows == 0:
        return {
            "query_success": True, "matched_rows": 0, "product_code": None, "symbol_raw": None,
            "expiry": None, "side": None, "quantity": None, "average_price": None,
            "market_price": None, "unrealized_pnl": None, "updated_at": value.get("updated_at"),
            "status": str(value.get("status") or "EMPTY"), "display_state": "EMPTY", "error_code": None,
        }
    if any(value.get(name) is None for name in _REQUIRED_POSITION_FIELDS):
        return sync_error("POSITION_FIELDS_INCOMPLETE")
    return {
        "query_success": True,
        "matched_rows": matched_rows,
        "product_code": str(value["product_code"]),
        "symbol_raw": str(value["symbol_raw"]),
        "expiry": str(value["expiry"]),
        "side": str(value["side"]),
        "quantity": int(value["quantity"]),
        "average_price": str(value["average_price"]),
        "market_price": str(value["market_price"]),
        "unrealized_pnl": str(value["unrealized_pnl"]),
        "updated_at": str(value["updated_at"]),
        "status": str(value["status"]),
        "display_state": "POSITION",
        "error_code": None,
    }


def read_position_snapshot(path: str | Path = DEFAULT_SNAPSHOT_PATH) -> dict[str, object]:
    snapshot_path = Path(path)
    if not snapshot_path.is_file():
        return sync_error("SNAPSHOT_MISSING")
    try:
        payload = json.loads(snapshot_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return sync_error("SNAPSHOT_UNREADABLE")
    if not isinstance(payload, Mapping):
        return sync_error("SNAPSHOT_SCHEMA_INVALID")
    return _position(payload)
