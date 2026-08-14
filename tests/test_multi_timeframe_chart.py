from datetime import UTC, datetime, timedelta

import pytest

from kam_market_ai.paper_trading.multi_timeframe_chart import (
    ChartCandle,
    ChartSeries,
    _recent_trend_anchors,
    render_multi_timeframe_chart_html,
)
from kam_market_ai.paper_trading.operator_presenter import PaperTradingOperatorView
from kam_market_ai.paper_trading.operator_wsgi import build_operator_wsgi


def test_chart_tooltip_stays_visible_long_enough_to_read() -> None:
    script = (
        __import__("pathlib").Path(__file__).parents[1]
        / "src"
        / "kam_market_ai"
        / "paper_trading"
        / "static"
        / "chart-refresh.js"
    ).read_text(encoding="utf-8")

    assert "const TOOLTIP_HIDE_DELAY_MS = 6000;" in script
    assert "hideChartTooltipLater(panel)" in script
    assert "document.hidden || isChartTooltipVisible()" in script
    assert 'event.key === "Escape"' in script
    assert "renderManualDrawings();" in script
    assert "window.localStorage.setItem(drawingStorageKey" in script
    assert 'activeDrawingTool === "horizontal"' in script


class FixtureChartSource:
    def read_series(self, instrument: str, timeframe: str) -> ChartSeries:
        start = datetime(2026, 8, 1, tzinfo=UTC)
        candles = tuple(
            ChartCandle(
                start + timedelta(hours=index),
                100 + index,
                102 + index,
                99 + index,
                101 + index,
                1000 + index,
            )
            for index in range(24)
        )
        return ChartSeries(
            instrument, timeframe, candles, "fixture-historical-bars", start + timedelta(hours=24)
        )


def _view() -> PaperTradingOperatorView:
    return PaperTradingOperatorView("KAM", "安全", {}, {}, {}, (), False)


def test_chart_page_is_fail_closed_without_historical_source() -> None:
    html = render_multi_timeframe_chart_html()
    assert (
        "多週期 K 線" in html
        and "15 分 K" in html
        and "60 分 K" in html
        and "日 K" in html
        and "週 K" in html
    )
    assert "資料不足" in html and "系統不補假資料" in html
    assert "<meta http-equiv='refresh'" not in html
    assert "<script src='/static/chart-refresh.js' defer></script>" in html
    assert "每 3 秒更新" in html
    assert "id='chart-summary'" in html and "id='chart-panel'" in html
    assert "<svg class='candlestick-chart'" not in html
    assert "趨勢／頸線｜手動畫線" in html and "支撐壓力｜資料不足" in html


def test_chart_page_shows_session_badges_from_source() -> None:
    class SessionSource(FixtureChartSource):
        def __init__(self, session: str) -> None:
            self.session = session

        def read_series(self, instrument: str, timeframe: str) -> ChartSeries:
            series = super().read_series(instrument, timeframe)
            return ChartSeries(
                series.instrument,
                series.timeframe,
                series.candles,
                series.source,
                series.updated_at,
                trading_session=self.session,
            )

    night_html = render_multi_timeframe_chart_html(SessionSource("afterhours"))
    day_html = render_multi_timeframe_chart_html(SessionSource("regular"))

    assert "chart-session-afterhours" in night_html and "夜盤" in night_html
    assert "chart-session-regular" in day_html and "日盤" in day_html


def test_chart_page_renders_injected_candles_ma20_volume_and_summary() -> None:
    html = render_multi_timeframe_chart_html(FixtureChartSource(), instrument="MTX", timeframe="1d")
    assert "<svg class='candlestick-chart'" in html
    assert html.count("<g class='chart-up'>") == 24
    assert "class='chart-ma20'" in html and "class='chart-volumes'" in html
    assert "日 K｜價格在 20MA 上方｜均線上彎" in html
    assert "fixture-historical-bars" in html and "任何單一指標均不構成進出場訊號" in html
    assert html.count("class='chart-hover-zone'") == 24
    assert "data-high='125'" in html and "data-low='122'" in html
    assert "data-ma20='114.5'" in html and "data-ma-label='20 日線'" in html
    assert "class='chart-crosshair'" in html and "class='chart-tooltip'" in html
    assert "class='chart-price-board'" in html
    assert "<span>最新收盤</span><strong>124</strong>" in html
    assert "<span>20 日線</span><strong>115</strong>" in html
    assert "<strong>114.50</strong>" not in html
    assert "<span>20 棒上壓力</span><strong>125</strong>" in html
    assert "<span>20 棒下支撐</span><strong>103</strong>" in html
    assert "20 棒支撐壓力已更新" in html
    assert "data-manual-tool='trend'" in html
    assert "data-manual-tool='horizontal'" in html
    assert "data-manual-action='undo'" in html
    assert "data-manual-action='clear'" in html
    assert "所有線均由手動畫線" in html
    assert "20 棒壓力／支撐｜僅數字參考" in html
    assert "chart-auto-level" not in html
    assert "class='chart-resistance-line'" not in html
    assert "class='chart-support-line'" not in html
    assert "class='chart-current-price'" not in html


def test_chart_page_renders_15m_reference_tab() -> None:
    html = render_multi_timeframe_chart_html(
        FixtureChartSource(), instrument="TMF", timeframe="15m"
    )

    assert "15 分 K｜價格在 20MA 上方｜均線上彎" in html
    assert "timeframe=15m" in html


def test_sparse_live_series_keeps_candle_bodies_at_readable_width() -> None:
    start = datetime(2026, 8, 13, tzinfo=UTC)

    class SparseSource:
        def read_series(self, instrument: str, timeframe: str) -> ChartSeries:
            candles = tuple(
                ChartCandle(start + timedelta(hours=index), 100, 103, 99, 102, 10)
                for index in range(3)
            )
            return ChartSeries(instrument, timeframe, candles, "sparse-live-bars", start)

    html = render_multi_timeframe_chart_html(SparseSource())

    assert html.count("width='11.00'") == 6
    assert "width='269.12'" not in html
    assert "已累積 3/20 根" in html
    assert "尚缺 17 根建立 20MA" in html
    assert "class='chart-current-line'" in html
    assert "<span>最新收盤</span><strong>102</strong>" in html
    assert "<span>20 棒上壓力</span><strong>—</strong>" in html
    assert "已完成 3/5 根；資料仍不足" in html
    assert "08/13 08:00" in html
    assert "data-ma20=''" in html


def test_60m_chart_limits_view_to_latest_48_bars_for_readable_spacing() -> None:
    start = datetime(2026, 8, 1, tzinfo=UTC)

    class DenseSource:
        def read_series(self, instrument: str, timeframe: str) -> ChartSeries:
            candles = tuple(
                ChartCandle(start + timedelta(hours=index), 100, 103, 99, 102, 10)
                for index in range(80)
            )
            return ChartSeries(instrument, timeframe, candles, "dense-60m", candles[-1].opened_at)

    html = render_multi_timeframe_chart_html(DenseSource(), timeframe="60m")

    assert html.count("class='chart-hover-zone'") == 48
    assert "width='9.90'" in html


def test_chart_uses_live_quote_for_current_line_without_changing_candle_close() -> None:
    start = datetime(2026, 8, 14, tzinfo=UTC)

    class LiveQuoteSource:
        def read_series(self, instrument: str, timeframe: str) -> ChartSeries:
            return ChartSeries(
                instrument,
                timeframe,
                (ChartCandle(start, 100, 103, 99, 102, 10),),
                "verified-bars+live-quote",
                start + timedelta(minutes=15),
                105,
                start + timedelta(minutes=12),
            )

    html = render_multi_timeframe_chart_html(LiveQuoteSource(), timeframe="15m")

    assert "<span>即時微台</span><strong>105</strong>" in html
    assert "富邦即時報價・每 3 秒刷新" in html
    assert "<span>最新收盤</span>" not in html
    assert "class='chart-current-price'" not in html
    assert "即時報價時間：2026-08-14T00:12:00+00:00" in html
    assert html.count("<g class='chart-up'>") == 1


def test_chart_marks_forming_daily_candle_as_display_only() -> None:
    start = datetime(2026, 8, 13, 16, tzinfo=UTC)

    class FormingSource:
        def read_series(self, instrument: str, timeframe: str) -> ChartSeries:
            return ChartSeries(
                instrument,
                timeframe,
                (ChartCandle(start, 100, 106, 99, 105, 10),),
                "taifex-closed+fubon-live",
                start + timedelta(hours=12),
                105,
                start + timedelta(hours=12),
                True,
                "本日形成中",
            )

    html = render_multi_timeframe_chart_html(FormingSource(), timeframe="1d")

    assert "class='chart-up chart-forming'" in html
    assert "本日形成中｜僅供顯示、不進入 KAM 或 Paper" in html
    assert "2026/08/14" in html


def test_chart_pressure_and_support_exclude_forming_candle() -> None:
    start = datetime(2026, 8, 1, tzinfo=UTC)

    class FormingRangeSource:
        def read_series(self, instrument: str, timeframe: str) -> ChartSeries:
            closed = tuple(
                ChartCandle(
                    start + timedelta(days=index),
                    100 + index,
                    102 + index,
                    99 + index,
                    101 + index,
                    10,
                )
                for index in range(20)
            )
            forming = ChartCandle(start + timedelta(days=20), 120, 999, 1, 121, 5)
            return ChartSeries(
                instrument,
                timeframe,
                (*closed, forming),
                "closed+forming",
                start + timedelta(days=20),
                121,
                start + timedelta(days=20),
                True,
                "本日形成中",
            )

    html = render_multi_timeframe_chart_html(FormingRangeSource(), timeframe="1d")

    assert "<span>20 棒上壓力</span><strong>121</strong>" in html
    assert "<span>20 棒下支撐</span><strong>99</strong>" in html
    assert "<span>20 棒上壓力</span><strong>999</strong>" not in html
    assert "最近 20 根已完成 K 棒" in html


def test_chart_draws_dominant_w_rising_and_nearest_falling_trend_lines() -> None:
    start = datetime(2026, 8, 1, tzinfo=UTC)
    lows = (10, 11, 8, 12, 13, 14, 10, 15, 14, 16, 11, 15, 14, 16, 17)
    highs = (20, 21, 18, 23, 25, 22, 19, 21, 23, 20, 19, 21, 22, 20, 19)

    class PivotSource:
        def read_series(self, instrument: str, timeframe: str) -> ChartSeries:
            candles = tuple(
                ChartCandle(
                    start + timedelta(hours=index),
                    (low + high) / 2,
                    high,
                    low,
                    (low + high) / 2,
                    10,
                )
                for index, (low, high) in enumerate(zip(lows, highs, strict=True))
            )
            return ChartSeries(instrument, timeframe, candles, "pivot-fixture", candles[-1].opened_at)

    html = render_multi_timeframe_chart_html(PivotSource(), timeframe="60m")
    rising, falling, neckline = _recent_trend_anchors(
        PivotSource().read_series("TMF", "60m")
    )

    assert "class='chart-rising-trend-line'" not in html
    assert "class='chart-falling-trend-line'" not in html
    assert "class='chart-neckline'" not in html
    assert "class='chart-manual-drawings'" in html
    assert rising is not None and rising[1:] == (10, start + timedelta(hours=12), 14)
    assert falling is not None and falling[1:] == (23, start + timedelta(hours=12), 22)
    assert neckline == (start + timedelta(hours=4), 25)


def test_chart_shows_live_price_number_on_three_second_refresh_line() -> None:
    html = render_multi_timeframe_chart_html(FixtureChartSource(), timeframe="60m")

    assert "class='chart-current-price-label'" in html
    assert ">即時 124</text>" in html


def test_old_resistance_is_not_mislabeled_as_w_neckline_without_right_recovery() -> None:
    start = datetime(2026, 8, 1, tzinfo=UTC)
    lows = (100, 94, 97, 95, 96, 97, 98, 99, 100)
    highs = (103, 97, 110, 98, 99, 100, 101, 102, 103)
    candles = tuple(
        ChartCandle(
            start + timedelta(hours=index),
            (low + high) / 2,
            high,
            low,
            (low + high) / 2,
            10,
        )
        for index, (low, high) in enumerate(zip(lows, highs, strict=True))
    )
    series = ChartSeries("TMF", "60m", candles, "resistance-only", candles[-1].opened_at)

    _, _, neckline = _recent_trend_anchors(series)
    html = render_multi_timeframe_chart_html(
        type("ResistanceSource", (), {"read_series": lambda self, instrument, timeframe: series})(),
        timeframe="60m",
    )

    assert neckline is None
    assert "class='chart-neckline'" not in html


def test_falling_line_connects_prominent_high_to_next_lower_wave_high() -> None:
    start = datetime(2026, 8, 1, tzinfo=UTC)
    highs = (104, 110, 105, 108, 104, 106, 102, 104, 100)
    lows = tuple(high - 4 for high in highs)
    candles = tuple(
        ChartCandle(
            start + timedelta(hours=index),
            high - 2,
            high,
            low,
            high - 2,
            10,
        )
        for index, (low, high) in enumerate(zip(lows, highs, strict=True))
    )
    series = ChartSeries("TMF", "60m", candles, "falling-waves", candles[-1].opened_at)

    _, falling, _ = _recent_trend_anchors(series)

    assert falling == (
        start + timedelta(hours=1),
        110,
        start + timedelta(hours=3),
        108,
    )


def test_broken_rising_trend_is_removed_until_a_new_structure_forms() -> None:
    start = datetime(2026, 8, 1, tzinfo=UTC)
    lows = (10, 11, 8, 12, 13, 14, 10, 15, 14, 16, 11, 15, 14, 16, 17, 5)
    highs = (20, 21, 18, 23, 25, 22, 19, 21, 23, 20, 19, 21, 22, 20, 19, 18)
    candles = tuple(
        ChartCandle(
            start + timedelta(hours=index),
            (low + high) / 2,
            high,
            low,
            (low + high) / 2,
            10,
        )
        for index, (low, high) in enumerate(zip(lows, highs, strict=True))
    )
    series = ChartSeries("TMF", "60m", candles, "broken-trend", candles[-1].opened_at)

    rising, _, neckline = _recent_trend_anchors(series)
    html = render_multi_timeframe_chart_html(
        type("BrokenSource", (), {"read_series": lambda self, instrument, timeframe: series})(),
        timeframe="60m",
    )

    assert rising is None
    assert neckline is not None
    assert "class='chart-rising-trend-line'" not in html


@pytest.mark.parametrize("instrument,timeframe", [("BAD", "60m"), ("TMF", "5m")])
def test_chart_page_rejects_unknown_instrument_or_timeframe(
    instrument: str, timeframe: str
) -> None:
    html = render_multi_timeframe_chart_html(
        FixtureChartSource(), instrument=instrument, timeframe=timeframe
    )
    assert "商品或週期無效" in html and "<svg class='candlestick-chart'" not in html


def test_wsgi_serves_get_only_chart_route_and_dashboard_link() -> None:
    app = build_operator_wsgi(_view, chart_data_source=FixtureChartSource())
    response = {}
    start = lambda status, headers: response.update(status=status, headers=headers)
    chart = b"".join(
        app(
            {
                "REQUEST_METHOD": "GET",
                "PATH_INFO": "/charts",
                "QUERY_STRING": "instrument=TX&timeframe=1w",
            },
            start,
        )
    ).decode()
    assert response["status"] == "200 OK" and "週 K｜價格在 20MA 上方" in chart
    dashboard = b"".join(app({"REQUEST_METHOD": "GET", "PATH_INFO": "/"}, start)).decode()
    assert "href='/charts'>多週期 K 線</a>" in dashboard
    b"".join(app({"REQUEST_METHOD": "POST", "PATH_INFO": "/charts"}, start))
    assert response["status"] == "405 Method Not Allowed"


def test_wsgi_serves_external_non_overlapping_chart_refresh_script() -> None:
    app = build_operator_wsgi(_view, chart_data_source=FixtureChartSource())
    response = {}
    start = lambda status, headers: response.update(status=status, headers=headers)

    script = b"".join(
        app({"REQUEST_METHOD": "GET", "PATH_INFO": "/static/chart-refresh.js"}, start)
    ).decode()

    assert response["status"] == "200 OK"
    assert ("Content-Type", "text/javascript; charset=utf-8") in response["headers"]
    assert "fetch(window.location.href" in script
    assert "window.setTimeout(refreshChart, REFRESH_INTERVAL_MS)" in script
    assert "refreshInFlight" in script
    assert "chart-summary" in script and "chart-panel" in script and "chart-footer" in script
    assert 'document.addEventListener("pointermove"' in script
    assert "zone.dataset.high" in script and "zone.dataset.low" in script
    assert "zone.dataset.ma20" in script and "尚未形成" in script
    assert 'maximumFractionDigits: 0' in script
