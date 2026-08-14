"""Read-only chart bridge with local normalized-candle continuity."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
import json
import os
from pathlib import Path
from threading import Lock

from kam_market_ai.paper_trading.multi_timeframe_chart import ChartCandle, ChartSeries

from .fubon_five_timeframe_pipeline import (
    CompleteFiveTimeframeCandleResult,
    FiveTimeframe,
    FiveTimeframeCandleResult,
)


class FubonLiveChartSource:
    """Merge verified live candles into a bounded local normalized history."""

    def __init__(
        self,
        result_provider: Callable[
            [], FiveTimeframeCandleResult | CompleteFiveTimeframeCandleResult | None
        ],
        *,
        history_path: str | Path | None = None,
        history_15m_path: str | Path | None = None,
        history_limit: int = 240,
    ) -> None:
        if not callable(result_provider):
            raise TypeError("result_provider must be callable")
        self._result_provider = result_provider
        if isinstance(history_limit, bool) or history_limit < 20:
            raise ValueError("history_limit must be at least 20")
        self._history_paths = {
            FiveTimeframe.M15: Path(history_15m_path) if history_15m_path is not None else None,
            FiveTimeframe.M60: Path(history_path) if history_path is not None else None,
        }
        self._history_limit = history_limit
        self._lock = Lock()

    @staticmethod
    def _chart_candles(result, selected: FiveTimeframe) -> tuple[ChartCandle, ...]:
        if result is None or selected not in result.series:
            return ()
        return tuple(
            ChartCandle(item.start, item.open, item.high, item.low, item.close, item.volume)
            for item in result.series[selected]
        )

    def _load_history(
        self, path: Path | None, timeframe: str
    ) -> tuple[ChartCandle, ...]:
        if path is None or not path.is_file():
            return ()
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if (
                payload.get("schema") != "kam-normalized-chart-history-v1"
                or payload.get("instrument") != "TMF"
                or payload.get("timeframe") != timeframe
            ):
                return ()
            return tuple(
                ChartCandle(
                    datetime.fromisoformat(row["opened_at"]),
                    float(row["open"]),
                    float(row["high"]),
                    float(row["low"]),
                    float(row["close"]),
                    int(row["volume"]),
                )
                for row in payload["candles"]
            )
        except (OSError, TypeError, ValueError, KeyError, json.JSONDecodeError):
            return ()

    def _write_history(
        self, path: Path | None, timeframe: str, candles: tuple[ChartCandle, ...]
    ) -> None:
        if path is None:
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema": "kam-normalized-chart-history-v1",
            "instrument": "TMF",
            "timeframe": timeframe,
            "candles": [
                {
                    "opened_at": item.opened_at.isoformat(),
                    "open": item.open,
                    "high": item.high,
                    "low": item.low,
                    "close": item.close,
                    "volume": item.volume,
                }
                for item in candles
            ],
        }
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        os.replace(temporary, path)

    def capture_latest(self) -> None:
        """Persist normalized verified 15/60-minute candles, never provider payloads."""
        result = self._result_provider()
        with self._lock:
            for selected, label in (
                (FiveTimeframe.M15, "15m"),
                (FiveTimeframe.M60, "60m"),
            ):
                path = self._history_paths[selected]
                live = self._chart_candles(result, selected)
                if not live or path is None:
                    continue
                merged = {
                    item.opened_at: item for item in self._load_history(path, label)
                }
                merged.update({item.opened_at: item for item in live})
                bounded = tuple(
                    sorted(merged.values(), key=lambda item: item.opened_at)
                )[-self._history_limit:]
                self._write_history(path, label, bounded)

    def read_series(self, instrument: str, timeframe: str) -> ChartSeries:
        mapping = {
            "15m": FiveTimeframe.M15,
            "60m": FiveTimeframe.M60,
            "1d": FiveTimeframe.DAY,
            "1w": FiveTimeframe.WEEK,
        }
        selected = mapping.get(timeframe)
        if instrument != "TMF" or selected is None:
            return ChartSeries(instrument, timeframe, (), "invalid-selection", None)
        result = self._result_provider()
        live = self._chart_candles(result, selected)
        history_path = self._history_paths.get(selected)
        if history_path is not None:
            self.capture_latest()
            with self._lock:
                history = self._load_history(history_path, timeframe)
            if history:
                return ChartSeries(
                    instrument,
                    timeframe,
                    history,
                    "fubon-live:normalized-local-history",
                    max(item.opened_at for item in history),
                )
        if not live:
            return ChartSeries(instrument, timeframe, (), "fubon-live:not-yet-verified", None)
        values = result.series[selected]
        updated_at = max((item.end for item in values), default=None)
        return ChartSeries(instrument, timeframe, live, "fubon-live:verified-candles", updated_at)


__all__ = ["FubonLiveChartSource"]
