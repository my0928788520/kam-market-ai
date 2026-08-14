from datetime import UTC, datetime, timedelta

import pytest

from kam_market_ai.paper_trading.multi_timeframe_chart import (
    ChartCandle,
    ChartSeries,
    render_multi_timeframe_chart_html,
)
from kam_market_ai.paper_trading.operator_presenter import PaperTradingOperatorView
from kam_market_ai.paper_trading.operator_wsgi import build_operator_wsgi


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
    assert "上升趨勢線｜尚未接入" in html and "支撐壓力｜尚未接入" in html


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
    assert "最新收盤 102" in html
    assert "08/13 08:00" in html
    assert "data-ma20=''" in html


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

    assert "即時 105" in html
    assert "最新收盤 102" not in html
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
