"""Deterministic, fail-closed export of explicitly verified historical candles.

This module owns no SDK, credentials, endpoint parameters, session calendar, or
timeframe aggregation rules.  A caller must inject an already configured,
market-data-only provider and an explicit plan whose intervals have been
verified against official provider documentation.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

from kam_market_ai.models import Candle, Instrument

CHART_HISTORY_EXPORT_VERSION = "kam-chart-history-v1"
MAX_EXPORTED_BARS = 100_000
_TIMEFRAME_INTERVALS = {"60m": 60, "1d": 1_440, "1w": 10_080}


class HistoricalCandleProvider(Protocol):
    async def historical_candles(
        self, instrument: Instrument, start: datetime, end: datetime, interval_minutes: int
    ) -> list[Candle]: ...


@dataclass(frozen=True, slots=True)
class HistoricalChartExportPlan:
    instruments: tuple[Instrument, ...]
    timeframes: tuple[str, ...]
    start: datetime
    end: datetime
    captured_at: datetime
    dataset_id: str
    dataset_version: str

    def __post_init__(self) -> None:
        for value, name in (
            (self.start, "start"),
            (self.end, "end"),
            (self.captured_at, "captured_at"),
        ):
            if value.tzinfo is None or value.utcoffset() is None:
                raise ValueError(f"{name} must be timezone-aware")
        if not self.instruments or any(
            value not in {Instrument.TX, Instrument.MTX} for value in self.instruments
        ):
            raise ValueError("only explicit TX/MTX historical exports are supported")
        if len(set(self.instruments)) != len(self.instruments):
            raise ValueError("duplicate instruments are not allowed")
        if not self.timeframes or any(
            value not in _TIMEFRAME_INTERVALS for value in self.timeframes
        ):
            raise ValueError("timeframes must be selected from 60m, 1d, and 1w")
        if len(set(self.timeframes)) != len(self.timeframes):
            raise ValueError("duplicate timeframes are not allowed")
        if not self.start < self.end <= self.captured_at:
            raise ValueError("export time range must be closed and not in the future")
        if not self.dataset_id.strip() or not self.dataset_version.strip():
            raise ValueError("dataset identity must be non-empty")


def _utc(value: datetime) -> datetime:
    return value.astimezone(UTC)


def _validate_candles(
    candles: list[Candle], instrument: Instrument, start: datetime, end: datetime
) -> tuple[Candle, ...]:
    if not candles:
        raise ValueError("HISTORY_EXPORT_EMPTY_SERIES")
    ordered = tuple(sorted(candles, key=lambda value: (value.start, value.end)))
    if len(ordered) > MAX_EXPORTED_BARS:
        raise ValueError("HISTORY_EXPORT_BAR_LIMIT_EXCEEDED")
    previous_end: datetime | None = None
    for candle in ordered:
        values = (candle.open, candle.high, candle.low, candle.close)
        if candle.instrument is not instrument or any(
            not isinstance(value, (int, float)) for value in values
        ):
            raise ValueError("HISTORY_EXPORT_CANDLE_INVALID")
        if candle.start.tzinfo is None or candle.end.tzinfo is None:
            raise ValueError("HISTORY_EXPORT_TIMESTAMP_INVALID")
        if not start <= candle.start < candle.end <= end:
            raise ValueError("HISTORY_EXPORT_CANDLE_OUT_OF_RANGE")
        if candle.low > min(values) or candle.high < max(values) or candle.volume < 0:
            raise ValueError("HISTORY_EXPORT_OHLCV_INVALID")
        if previous_end is not None and candle.start < previous_end:
            raise ValueError("HISTORY_EXPORT_OVERLAPPING_BARS")
        previous_end = candle.end
    return ordered


async def build_historical_chart_export(
    provider: HistoricalCandleProvider, plan: HistoricalChartExportPlan
) -> dict[str, object]:
    rows: list[dict[str, object]] = []
    sequence = 0
    for instrument in sorted(plan.instruments, key=lambda value: value.value):
        for timeframe in sorted(plan.timeframes, key=lambda value: _TIMEFRAME_INTERVALS[value]):
            candles = await provider.historical_candles(
                instrument, plan.start, plan.end, _TIMEFRAME_INTERVALS[timeframe]
            )
            for candle in _validate_candles(candles, instrument, plan.start, plan.end):
                sequence += 1
                rows.append(
                    {
                        "instrument": instrument.value,
                        "timeframe": timeframe,
                        "opened_at": _utc(candle.start).isoformat(),
                        "closed_at": _utc(candle.end).isoformat(),
                        "open": str(candle.open),
                        "high": str(candle.high),
                        "low": str(candle.low),
                        "close": str(candle.close),
                        "volume": str(candle.volume),
                        "source_record_id": f"{instrument.value}-{timeframe}-{sequence:06d}",
                        "closed": True,
                    }
                )
    canonical_bars = json.dumps(rows, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return {
        "export_version": CHART_HISTORY_EXPORT_VERSION,
        "dataset_id": plan.dataset_id,
        "dataset_version": plan.dataset_version,
        "captured_at": _utc(plan.captured_at).isoformat(),
        "bars_sha256": hashlib.sha256(canonical_bars.encode("utf-8")).hexdigest(),
        "bars": rows,
    }


def write_historical_chart_export(path: str | Path, payload: dict[str, object]) -> Path:
    """Atomically create one export and refuse to replace existing evidence."""
    selected = Path(path)
    if not selected.is_absolute():
        raise ValueError("HISTORY_EXPORT_PATH_MUST_BE_ABSOLUTE")
    if selected.exists():
        raise FileExistsError("HISTORY_EXPORT_ALREADY_EXISTS")
    selected.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    descriptor, temporary = tempfile.mkstemp(
        prefix=f".{selected.name}.", suffix=".tmp", dir=selected.parent
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(serialized)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, selected)
    except BaseException:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise
    return selected


__all__ = [
    "CHART_HISTORY_EXPORT_VERSION",
    "HistoricalChartExportPlan",
    "build_historical_chart_export",
    "write_historical_chart_export",
]
