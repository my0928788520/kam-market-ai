"""Immutable, SDK-independent position parsing models."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any, Mapping


class PositionSide(StrEnum):
    LONG = "LONG"
    SHORT = "SHORT"
    UNKNOWN = "UNKNOWN"


class ParseStatus(StrEnum):
    NORMALIZED = "NORMALIZED"
    PARTIAL = "PARTIAL"
    REJECTED = "REJECTED"


class MatchStatus(StrEnum):
    SINGLE_MTX_POSITION = "SINGLE_MTX_POSITION"
    NOT_SINGLE_MTX_POSITION = "NOT_SINGLE_MTX_POSITION"
    EMPTY = "EMPTY"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True, slots=True)
class RawPositionRow:
    source_index: int
    payload: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class RawPositionCapture:
    rows: tuple[RawPositionRow, ...]
    captured_at: datetime
    source: str = "offline-fixture"
    schema_version: str = "V2.3.1"

    @classmethod
    def from_rows(cls, rows: tuple[RawPositionRow, ...], *, source: str = "offline-fixture") -> "RawPositionCapture":
        return cls(rows=rows, captured_at=datetime.now(UTC), source=source)


@dataclass(frozen=True, slots=True)
class NormalizedFuturesPosition:
    source_index: int
    symbol_raw: str | None
    product_raw: str | None
    product_code: str | None
    contract_month: str | None
    side: PositionSide
    quantity: int | None
    average_price: Decimal | None
    current_price: Decimal | None
    unrealized_pnl: Decimal | None
    status: ParseStatus
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class MatchedPosition:
    contract_month: str | None
    long_quantity: int
    short_quantity: int
    net_quantity: int
    side: PositionSide
    source_indexes: tuple[int, ...]
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class MatchedPositionReport:
    status: MatchStatus
    positions: tuple[MatchedPosition, ...]
    unmatched_source_indexes: tuple[int, ...]
    warnings: tuple[str, ...] = ()


def json_value(value: Any) -> Any:
    """Convert position models to deterministic JSON-safe values."""
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, tuple):
        return [json_value(item) for item in value]
    if isinstance(value, list):
        return [json_value(item) for item in value]
    if isinstance(value, Mapping):
        return {str(key): json_value(item) for key, item in value.items()}
    if hasattr(value, "__dataclass_fields__"):
        return json_value(asdict(value))
    return value
