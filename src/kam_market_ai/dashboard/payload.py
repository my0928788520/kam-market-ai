"""Root Dashboard payload builder; only position is live in V2.3.1."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from .position_reader import DEFAULT_SNAPSHOT_PATH, read_position_snapshot


def build_dashboard_payload(snapshot_path: str | Path = DEFAULT_SNAPSHOT_PATH) -> dict[str, object]:
    return {
        "schema_version": "V2.3.1",
        "generated_at": datetime.now(UTC).isoformat(),
        "market_summary": {"status": "STATIC", "message": "市場資料尚未接通"},
        "market_direction": {"status": "STATIC", "message": "尚未接通"},
        "market_control": {"status": "STATIC", "message": "尚未接通"},
        "market_lifecycle": {
            "status": "STATIC", "shape": "INVERTED_U",
            "message": "倒 U 市場生命週期區塊保留，尚未接通市場資料",
        },
        "timeframes": {"status": "STATIC", "periods": ["1W", "1D", "60m", "15m"]},
        "position": read_position_snapshot(snapshot_path),
        "next_step": {"status": "STATIC", "message": "尚未接通決策引擎"},
    }
