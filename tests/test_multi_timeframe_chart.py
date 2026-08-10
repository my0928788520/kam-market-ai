from datetime import UTC, datetime, timedelta

import pytest

from kam_market_ai.paper_trading.multi_timeframe_chart import ChartCandle, ChartSeries, render_multi_timeframe_chart_html
from kam_market_ai.paper_trading.operator_presenter import PaperTradingOperatorView
from kam_market_ai.paper_trading.operator_wsgi import build_operator_wsgi


class FixtureChartSource:
    def read_series(self, instrument: str, timeframe: str) -> ChartSeries:
        start = datetime(2026, 8, 1, tzinfo=UTC)
        candles = tuple(ChartCandle(start + timedelta(hours=index), 100 + index, 102 + index, 99 + index, 101 + index, 1000 + index) for index in range(24))
        return ChartSeries(instrument, timeframe, candles, "fixture-historical-bars", start + timedelta(hours=24))


def _view() -> PaperTradingOperatorView:
    return PaperTradingOperatorView("KAM", "安全", {}, {}, {}, (), False)


def test_chart_page_is_fail_closed_without_historical_source() -> None:
    html = render_multi_timeframe_chart_html()
    assert "多週期 K 線" in html and "60 分 K" in html and "日 K" in html and "週 K" in html
    assert "資料不足" in html and "系統不補假資料" in html
    assert "<svg class='candlestick-chart'" not in html
    assert "上升趨勢線｜尚未接入" in html and "支撐壓力｜尚未接入" in html


def test_chart_page_renders_injected_candles_ma20_volume_and_summary() -> None:
    html = render_multi_timeframe_chart_html(FixtureChartSource(), instrument="MTX", timeframe="1d")
    assert "<svg class='candlestick-chart'" in html
    assert html.count("<g class='chart-up'>") == 24
    assert "class='chart-ma20'" in html and "class='chart-volumes'" in html
    assert "日 K｜價格在 20MA 上方｜均線上彎" in html
    assert "fixture-historical-bars" in html and "任何單一指標均不構成進出場訊號" in html


@pytest.mark.parametrize("instrument,timeframe", [("BAD", "60m"), ("TMF", "5m")])
def test_chart_page_rejects_unknown_instrument_or_timeframe(instrument: str, timeframe: str) -> None:
    html = render_multi_timeframe_chart_html(FixtureChartSource(), instrument=instrument, timeframe=timeframe)
    assert "商品或週期無效" in html and "<svg class='candlestick-chart'" not in html


def test_wsgi_serves_get_only_chart_route_and_dashboard_link() -> None:
    app = build_operator_wsgi(_view, chart_data_source=FixtureChartSource())
    response = {}
    start = lambda status, headers: response.update(status=status, headers=headers)
    chart = b"".join(app({"REQUEST_METHOD": "GET", "PATH_INFO": "/charts", "QUERY_STRING": "instrument=TX&timeframe=1w"}, start)).decode()
    assert response["status"] == "200 OK" and "週 K｜價格在 20MA 上方" in chart
    dashboard = b"".join(app({"REQUEST_METHOD": "GET", "PATH_INFO": "/"}, start)).decode()
    assert "href='/charts'>多週期 K 線</a>" in dashboard
    b"".join(app({"REQUEST_METHOD": "POST", "PATH_INFO": "/charts"}, start))
    assert response["status"] == "405 Method Not Allowed"
