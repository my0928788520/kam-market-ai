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
        history_limit: int = 240,
    ) -> None:
        if not callable(result_provider):
            raise TypeError("result_provider must be callable")
        self._result_provider = result_provider
        if isinstance(history_limit, bool) or history_limit < 20:
            raise ValueError("history_limit must be at least 20")
        self._history_path = Path(history_path) if history_path is not None else None
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

    def _load_history(self) -> tuple[ChartCandle, ...]:
        if self._history_path is None or not self._history_path.is_file():
            return ()
        try:
            payload = json.loads(self._history_path.read_text(encoding="utf-8"))
            if payload.get("schema") != "kam-normalized-chart-history-v1":
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

    def _write_history(self, candles: tuple[ChartCandle, ...]) -> None:
        if self._history_path is None:
            return
        self._history_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema": "kam-normalized-chart-history-v1",
            "instrument": "TMF",
            "timeframe": "60m",
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
        temporary = self._history_path.with_suffix(self._history_path.suffix + ".tmp")
        temporary.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        os.replace(temporary, self._history_path)

    def capture_latest(self) -> None:
        """Persist only normalized verified 60-minute candles, never provider payloads."""
        live = self._chart_candles(self._result_provider(), FiveTimeframe.M60)
        if not live or self._history_path is None:
            return
        with self._lock:
            merged = {item.opened_at: item for item in self._load_history()}
            merged.update({item.opened_at: item for item in live})
            bounded = tuple(sorted(merged.values(), key=lambda item: item.opened_at))[-self._history_limit:]
            self._write_history(bounded)

    def read_series(self, instrument: str, timeframe: str) -> ChartSeries:
        mapping = {"60m": FiveTimeframe.M60, "1d": FiveTimeframe.DAY, "1w": FiveTimeframe.WEEK}
        selected = mapping.get(timeframe)
        if instrument != "TMF" or selected is None:
            return ChartSeries(instrument, timeframe, (), "invalid-selection", None)
        result = self._result_provider()
        live = self._chart_candles(result, selected)
        if selected is FiveTimeframe.M60 and self._history_path is not None:
            self.capture_latest()
            with self._lock:
                history = self._load_history()
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
