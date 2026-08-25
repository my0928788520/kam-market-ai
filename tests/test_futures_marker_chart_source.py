from datetime import UTC, datetime
from decimal import Decimal

from kam_market_ai.paper_trading.contracts import PaperTradingSide
from kam_market_ai.paper_trading.futures_chart_markers import (
    FuturesPaperMarkerAction,
    build_futures_paper_markers_from_events,
)
from kam_market_ai.paper_trading.futures_marker_chart_source import (
    FuturesPaperMarkerChartSource,
)
from kam_market_ai.paper_trading.live_tmf_simulation import (
    TmfPaperPerformanceEvent,
    TmfPaperPerformanceEventType,
)
from kam_market_ai.paper_trading.multi_timeframe_chart import ChartSeries


NOW = datetime(2026, 8, 25, 23, 55, tzinfo=UTC)
HASH = "a" * 64


def event(
    event_type: TmfPaperPerformanceEventType,
    side: PaperTradingSide,
    *,
    minute: int,
    current: str,
    realized: str = "0",
) -> TmfPaperPerformanceEvent:
    entry = Decimal("100")
    stop = Decimal("90") if side is PaperTradingSide.BUY else Decimal("110")
    target = Decimal("110") if side is PaperTradingSide.BUY else Decimal("90")
    return TmfPaperPerformanceEvent(
        event_type,
        f"trade-{side.value}-{minute}",
        "TMFI6",
        Decimal("1"),
        entry,
        Decimal(current),
        stop,
        target,
        Decimal("0"),
        Decimal(realized),
        Decimal("0"),
        Decimal("0"),
        NOW.replace(minute=minute),
        HASH,
        HASH,
        HASH,
        None,
        position_side=side,
    )


def test_verified_journal_events_map_to_four_futures_chart_actions() -> None:
    events = (
        event(TmfPaperPerformanceEventType.ENTRY, PaperTradingSide.BUY, minute=1, current="100"),
        event(TmfPaperPerformanceEventType.TAKE_PROFIT_EXIT, PaperTradingSide.BUY, minute=2, current="105", realized="50"),
        event(TmfPaperPerformanceEventType.ENTRY, PaperTradingSide.SELL, minute=3, current="100"),
        event(TmfPaperPerformanceEventType.TAKE_PROFIT_EXIT, PaperTradingSide.SELL, minute=4, current="95", realized="50"),
    )

    markers = build_futures_paper_markers_from_events(events, chart_instrument="TMF")

    assert tuple(marker.action for marker in markers) == (
        FuturesPaperMarkerAction.LONG_ENTRY,
        FuturesPaperMarkerAction.LONG_EXIT,
        FuturesPaperMarkerAction.SHORT_ENTRY,
        FuturesPaperMarkerAction.SHORT_COVER,
    )
    assert tuple(marker.price for marker in markers) == (
        Decimal("100"),
        Decimal("105"),
        Decimal("100"),
        Decimal("95"),
    )
    assert all(marker.source == "verified_tmf_paper_journal" for marker in markers)


def test_chart_source_decorator_preserves_lifecycle_and_adds_current_journal() -> None:
    entries = [event(TmfPaperPerformanceEventType.ENTRY, PaperTradingSide.BUY, minute=1, current="100")]

    class Source:
        capture_count = 0

        def capture_latest(self) -> None:
            self.capture_count += 1

        def read_series(self, instrument: str, timeframe: str) -> ChartSeries:
            return ChartSeries(instrument, timeframe, (), "live", NOW)

    source = Source()
    decorated = FuturesPaperMarkerChartSource(source, lambda: tuple(entries))
    decorated.capture_latest()
    first = decorated.read_series("TMF", "60m")
    entries.append(
        event(
            TmfPaperPerformanceEventType.TAKE_PROFIT_EXIT,
            PaperTradingSide.BUY,
            minute=2,
            current="105",
            realized="50",
        )
    )
    second = decorated.read_series("TMF", "60m")

    assert source.capture_count == 1
    assert len(first.paper_markers) == 1
    assert len(second.paper_markers) == 2
