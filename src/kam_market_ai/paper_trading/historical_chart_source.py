"""Fail-closed bridge from exported historical OHLCV JSON to chart read models."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from json import JSONDecodeError, dumps, loads
from pathlib import Path

from kam_market_ai.market_data.historical_feed import OfflineHistoricalDataset, read_historical_feed
from kam_market_ai.market_data.provider_adapter import OfflineMarketDataSource, OfflineMarketDataSourceKind
from kam_market_ai.market_data.provider_contract import (
    MarketDataProviderContract, MarketDataRequest, MarketDataTimeframe,
    ProviderResponseStatus, ResearchSourceKind,
)

from .multi_timeframe_chart import ChartCandle, ChartSeries

MAX_CHART_HISTORY_BYTES = 10 * 1024 * 1024
_TIMEFRAMES = {"60m": MarketDataTimeframe.M60, "1d": MarketDataTimeframe.DAY, "1w": MarketDataTimeframe.WEEK}


@dataclass(frozen=True, slots=True)
class ExportedHistoricalChartSource:
    """Read a validated, immutable snapshot of explicitly supplied JSON bars."""
    rows: tuple[dict[str, object], ...]
    dataset_id: str
    dataset_version: str
    captured_at: datetime

    def __post_init__(self) -> None:
        if self.captured_at.tzinfo is None or self.captured_at.utcoffset() is None:
            raise ValueError("captured_at must be timezone-aware")
        if not self.dataset_id.strip() or not self.dataset_version.strip():
            raise ValueError("dataset identity must be non-empty")

    def read_series(self, instrument: str, timeframe: str) -> ChartSeries:
        selected_timeframe = _TIMEFRAMES.get(timeframe)
        if instrument not in {"TX", "MTX", "TMF"} or selected_timeframe is None:
            return ChartSeries(instrument, timeframe, (), "invalid-selection", None)
        matching = tuple(row for row in self.rows if row.get("instrument") == instrument and row.get("timeframe") == timeframe)
        if not matching:
            return ChartSeries(instrument, timeframe, (), f"{self.dataset_id}:no-matching-bars", self.captured_at)
        try:
            opened = tuple(_timestamp(row.get("opened_at")) for row in matching)
            closed = tuple(_timestamp(row.get("closed_at")) for row in matching)
            provider = MarketDataProviderContract(
                f"chart-json:{self.dataset_id}", self.dataset_version,
                ResearchSourceKind.FIXTURE, (selected_timeframe,),
            )
            request = MarketDataRequest(
                provider.provider_id, instrument, selected_timeframe,
                min(opened), max(closed), self.captured_at,
            )
            dataset = OfflineHistoricalDataset(
                self.dataset_id, self.dataset_version, self.captured_at,
                OfflineMarketDataSource(
                    OfflineMarketDataSourceKind.JSON,
                    dumps(matching, sort_keys=True, separators=(",", ":"), default=str),
                ),
            )
            result = read_historical_feed(provider, request, dataset)
        except (TypeError, ValueError):
            return ChartSeries(instrument, timeframe, (), f"{self.dataset_id}:blocked", self.captured_at)
        if result.response.status is not ProviderResponseStatus.READY:
            issue = result.response.issue_codes[0] if result.response.issue_codes else "blocked"
            return ChartSeries(instrument, timeframe, (), f"{self.dataset_id}:blocked:{issue}", self.captured_at)
        candles = tuple(ChartCandle(
            bar.opened_at, float(bar.open), float(bar.high), float(bar.low),
            float(bar.close), int(bar.volume or 0),
        ) for bar in result.response.bars)
        return ChartSeries(
            instrument, timeframe, candles,
            f"{self.dataset_id}@{self.dataset_version}｜{result.feed_hash[:12]}", self.captured_at,
        )


def _timestamp(value: object) -> datetime:
    if not isinstance(value, str):
        raise ValueError("timestamp must be an ISO-8601 string")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("timestamp must be timezone-aware")
    return parsed


def load_exported_historical_chart_source(path: str | Path) -> ExportedHistoricalChartSource:
    """Load one bounded local JSON export; never performs network or broker I/O."""
    selected = Path(path)
    size = selected.stat().st_size
    if size <= 0 or size > MAX_CHART_HISTORY_BYTES:
        raise ValueError("CHART_HISTORY_FILE_SIZE_INVALID")
    try:
        payload = loads(selected.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, JSONDecodeError) as error:
        raise ValueError("CHART_HISTORY_JSON_INVALID") from error
    if not isinstance(payload, dict) or not isinstance(payload.get("bars"), list):
        raise ValueError("CHART_HISTORY_ROOT_INVALID")
    rows = tuple(payload["bars"])
    if not rows or any(not isinstance(row, dict) for row in rows):
        raise ValueError("CHART_HISTORY_BARS_INVALID")
    captured_at = _timestamp(payload.get("captured_at"))
    if captured_at > datetime.now(timezone.utc):
        raise ValueError("CHART_HISTORY_CAPTURED_AT_IN_FUTURE")
    return ExportedHistoricalChartSource(
        rows, str(payload.get("dataset_id", "")),
        str(payload.get("dataset_version", "")), captured_at,
    )


__all__ = ["ExportedHistoricalChartSource", "MAX_CHART_HISTORY_BYTES", "load_exported_historical_chart_source"]
