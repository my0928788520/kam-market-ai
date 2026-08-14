"""In-memory, read-only chart bridge for the latest verified Fubon candles."""

from __future__ import annotations

from collections.abc import Callable

from kam_market_ai.paper_trading.multi_timeframe_chart import ChartCandle, ChartSeries

from .fubon_five_timeframe_pipeline import (
    CompleteFiveTimeframeCandleResult,
    FiveTimeframe,
    FiveTimeframeCandleResult,
)


class FubonLiveChartSource:
    """Expose latest immutable candles to the local chart without writing raw data."""

    def __init__(
        self,
        result_provider: Callable[
            [], FiveTimeframeCandleResult | CompleteFiveTimeframeCandleResult | None
        ],
    ) -> None:
        if not callable(result_provider):
            raise TypeError("result_provider must be callable")
        self._result_provider = result_provider

    def read_series(self, instrument: str, timeframe: str) -> ChartSeries:
        mapping = {"60m": FiveTimeframe.M60, "1d": FiveTimeframe.DAY, "1w": FiveTimeframe.WEEK}
        selected = mapping.get(timeframe)
        if instrument != "TMF" or selected is None:
            return ChartSeries(instrument, timeframe, (), "invalid-selection", None)
        result = self._result_provider()
        if result is None or selected not in result.series:
            return ChartSeries(instrument, timeframe, (), "fubon-live:not-yet-verified", None)
        values = result.series[selected]
        candles = tuple(
            ChartCandle(
                item.start,
                item.open,
                item.high,
                item.low,
                item.close,
                item.volume,
            )
            for item in values
        )
        updated_at = max((item.end for item in values), default=None)
        return ChartSeries(instrument, timeframe, candles, "fubon-live:verified-candles", updated_at)


__all__ = ["FubonLiveChartSource"]
