"""Pure, offline adapters for replay, fixture, JSON, and CSV market data."""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from csv import DictReader
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from io import StringIO
from json import JSONDecodeError, loads

from .provider_contract import (
    MarketDataBar,
    MarketDataProviderContract,
    MarketDataProviderResponse,
    MarketDataRequest,
    MarketDataTimeframe,
    ProviderResponseStatus,
)


MARKET_DATA_PROVIDER_ADAPTER_VERSION = "1.0"
REQUIRED_BAR_FIELDS = frozenset(
    {
        "instrument", "timeframe", "opened_at", "closed_at", "open", "high", "low",
        "close", "volume", "source_record_id",
    }
)


class OfflineMarketDataSourceKind(StrEnum):
    REPLAY = "replay"
    FIXTURE = "fixture"
    JSON = "json"
    CSV = "csv"


@dataclass(frozen=True, slots=True)
class OfflineMarketDataSource:
    source_kind: OfflineMarketDataSourceKind
    content: Sequence[Mapping[str, object]] | str
    source_version: str = "1.0"

    def __post_init__(self) -> None:
        if not self.source_version.strip():
            raise ValueError("source_version must be non-empty.")
        if self.source_kind in {OfflineMarketDataSourceKind.REPLAY, OfflineMarketDataSourceKind.FIXTURE}:
            if isinstance(self.content, str) or not isinstance(self.content, Sequence):
                raise ValueError("Replay and fixture sources require a sequence of mappings.")
        elif not isinstance(self.content, str):
            raise ValueError("JSON and CSV sources require text content.")


def _parse_time(value: object) -> datetime:
    if not isinstance(value, str):
        raise ValueError("timestamp must be an ISO-8601 string.")
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _parse_closed(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str) and value.strip().lower() in {"true", "false"}:
        return value.strip().lower() == "true"
    raise ValueError("closed must be a boolean.")


def _parse_decimal(value: object, field_name: str) -> Decimal:
    if isinstance(value, bool):
        raise ValueError(f"{field_name} must be numeric.")
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError) as error:
        raise ValueError(f"{field_name} must be numeric.") from error


def _rows(source: OfflineMarketDataSource) -> tuple[Mapping[str, object], ...]:
    if source.source_kind in {OfflineMarketDataSourceKind.REPLAY, OfflineMarketDataSourceKind.FIXTURE}:
        rows = tuple(source.content)  # type: ignore[arg-type]
    elif source.source_kind is OfflineMarketDataSourceKind.JSON:
        try:
            decoded = loads(source.content)  # type: ignore[arg-type]
        except JSONDecodeError as error:
            raise ValueError("INVALID_JSON") from error
        if not isinstance(decoded, list):
            raise ValueError("JSON_ROOT_MUST_BE_ARRAY")
        rows = tuple(decoded)
    else:
        rows = tuple(DictReader(StringIO(source.content)))  # type: ignore[arg-type]
    if any(not isinstance(row, Mapping) for row in rows):
        raise ValueError("ROW_MUST_BE_MAPPING")
    return rows


def _bar(row: Mapping[str, object]) -> MarketDataBar:
    if not REQUIRED_BAR_FIELDS.issubset(row):
        raise ValueError("MISSING_REQUIRED_BAR_FIELD")
    timeframe = MarketDataTimeframe(str(row["timeframe"]))
    volume_value = row["volume"]
    return MarketDataBar(
        instrument=str(row["instrument"]),
        timeframe=timeframe,
        opened_at=_parse_time(row["opened_at"]),
        closed_at=_parse_time(row["closed_at"]),
        open=_parse_decimal(row["open"], "open"),
        high=_parse_decimal(row["high"], "high"),
        low=_parse_decimal(row["low"], "low"),
        close=_parse_decimal(row["close"], "close"),
        volume=None if volume_value in {None, ""} else _parse_decimal(volume_value, "volume"),
        source_record_id=str(row["source_record_id"]),
        closed=_parse_closed(row.get("closed", True)),
    )


def _blocked(provider: MarketDataProviderContract, request: MarketDataRequest, code: str) -> MarketDataProviderResponse:
    return MarketDataProviderResponse(provider, request, ProviderResponseStatus.BLOCKED, (), (code,))


def adapt_offline_market_data(
    provider: MarketDataProviderContract,
    request: MarketDataRequest,
    source: OfflineMarketDataSource,
) -> MarketDataProviderResponse:
    """Adapt supplied offline content to a deterministic provider response.

    Source parsing and response construction are entirely in-memory.  Invalid
    source data becomes a BLOCKED response; no rows are silently repaired.
    """
    try:
        parsed = tuple(_bar(row) for row in _rows(source))
        selected = tuple(
            sorted(
                (
                    bar
                    for bar in parsed
                    if bar.instrument == request.instrument
                    and bar.timeframe is request.timeframe
                    and request.start_at <= bar.opened_at
                    and bar.closed_at <= request.end_at
                ),
                key=lambda bar: (bar.opened_at, bar.source_record_id),
            )
        )
        if not selected:
            return MarketDataProviderResponse(
                provider, request, ProviderResponseStatus.INSUFFICIENT_DATA, (), ("NO_MATCHING_OFFLINE_BARS",)
            )
        return MarketDataProviderResponse(provider, request, ProviderResponseStatus.READY, selected)
    except (TypeError, ValueError) as error:
        return _blocked(provider, request, str(error) or "INVALID_OFFLINE_SOURCE")
