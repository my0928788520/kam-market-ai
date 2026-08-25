"""Read-only chart source decorator for verified Paper Trading journal markers."""

from __future__ import annotations

from dataclasses import replace
from typing import Callable

from .futures_chart_markers import build_futures_paper_markers_from_events
from .multi_timeframe_chart import ChartSeries


class FuturesPaperMarkerChartSource:
    """Decorate a chart source without changing its market-data lifecycle."""

    def __init__(
        self,
        source: object,
        events_provider: Callable[[], tuple[object, ...]],
    ) -> None:
        if not callable(getattr(source, "read_series", None)):
            raise TypeError("source must provide read_series")
        if not callable(events_provider):
            raise TypeError("events_provider must be callable")
        self._source = source
        self._events_provider = events_provider

    def __getattr__(self, name: str) -> object:
        return getattr(self._source, name)

    def _enrich(self, series: ChartSeries) -> ChartSeries:
        if not isinstance(series, ChartSeries):
            raise TypeError("decorated source must return ChartSeries")
        markers = build_futures_paper_markers_from_events(
            self._events_provider(),
            chart_instrument=series.instrument,
        )
        return replace(series, paper_markers=markers)

    def read_series(self, instrument: str, timeframe: str) -> ChartSeries:
        return self._enrich(self._source.read_series(instrument, timeframe))

    def read_series_for_session(
        self,
        instrument: str,
        timeframe: str,
        view_session: str,
    ) -> ChartSeries:
        reader = getattr(self._source, "read_series_for_session", None)
        if callable(reader):
            return self._enrich(reader(instrument, timeframe, view_session))
        return self.read_series(instrument, timeframe)
