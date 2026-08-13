"""Safe file projection for live five-timeframe verifier output."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path

_FORBIDDEN_KEYS = frozenset({"candles", "series", "raw_payload", "orders", "positions"})


def _validate(value: object) -> dict[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError("FIVE_TIMEFRAME_SNAPSHOT_OBJECT_REQUIRED")
    payload = dict(value)
    if payload.get("market_data_only") is not True:
        raise ValueError("FIVE_TIMEFRAME_SNAPSHOT_MARKET_DATA_ONLY_REQUIRED")
    if payload.get("trading_enabled") is not False:
        raise ValueError("FIVE_TIMEFRAME_SNAPSHOT_TRADING_MUST_BE_DISABLED")
    if payload.get("live_order_allowed") is not False:
        raise ValueError("FIVE_TIMEFRAME_SNAPSHOT_LIVE_ORDER_MUST_BE_DISABLED")

    def walk(item: object) -> None:
        if isinstance(item, Mapping):
            if _FORBIDDEN_KEYS.intersection(str(key).lower() for key in item):
                raise ValueError("FIVE_TIMEFRAME_SNAPSHOT_FORBIDDEN_RAW_DATA")
            for nested in item.values():
                walk(nested)
        elif isinstance(item, list):
            for nested in item:
                walk(nested)

    walk(payload)
    return payload


def write_five_timeframe_snapshot(path: str | Path, payload: Mapping[str, object]) -> Path:
    """Replace one local safe snapshot without retaining provider payloads."""
    target = Path(path)
    safe = _validate(payload)
    temporary = target.with_suffix(target.suffix + ".tmp")
    temporary.write_text(json.dumps(safe, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(target)
    return target


def read_five_timeframe_snapshot(path: str | Path) -> dict[str, object]:
    return _validate(json.loads(Path(path).read_text(encoding="utf-8")))


__all__ = ["read_five_timeframe_snapshot", "write_five_timeframe_snapshot"]
