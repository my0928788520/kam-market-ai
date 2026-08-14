"""GET-only multi-timeframe chart read model and SVG renderer."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from html import escape
from math import isfinite
from typing import Protocol

SUPPORTED_CHART_TIMEFRAMES = ("60m", "1d", "1w")
TIMEFRAME_LABELS = {"60m": "60 分 K", "1d": "日 K", "1w": "週 K"}


@dataclass(frozen=True, slots=True)
class ChartCandle:
    opened_at: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int

    def __post_init__(self) -> None:
        prices = (self.open, self.high, self.low, self.close)
        if self.opened_at.tzinfo is None or self.opened_at.utcoffset() is None:
            raise ValueError("opened_at must be timezone-aware")
        if not all(isfinite(value) for value in prices):
            raise ValueError("prices must be finite")
        if self.high < max(self.open, self.close) or self.low > min(self.open, self.close):
            raise ValueError("invalid OHLC bounds")
        if self.volume < 0:
            raise ValueError("volume must be non-negative")


@dataclass(frozen=True, slots=True)
class ChartSeries:
    instrument: str
    timeframe: str
    candles: tuple[ChartCandle, ...]
    source: str
    updated_at: datetime | None


class ChartDataReadOnlySource(Protocol):
    def read_series(self, instrument: str, timeframe: str) -> ChartSeries: ...


class EmptyChartDataSource:
    """Production-safe default until a historical provider is connected."""

    def read_series(self, instrument: str, timeframe: str) -> ChartSeries:
        return ChartSeries(instrument, timeframe, (), "historical-source-not-connected", None)


EMPTY_CHART_DATA_SOURCE = EmptyChartDataSource()


def _ma20(candles: tuple[ChartCandle, ...]) -> tuple[float | None, ...]:
    values: list[float | None] = []
    running = 0.0
    for index, candle in enumerate(candles):
        running += candle.close
        if index >= 20:
            running -= candles[index - 20].close
        values.append(running / 20 if index >= 19 else None)
    return tuple(values)


def _summary(series: ChartSeries, ma_values: tuple[float | None, ...]) -> str:
    if not series.candles:
        return f"{TIMEFRAME_LABELS.get(series.timeframe, '週期無效')}｜資料不足"
    latest_ma = ma_values[-1]
    if latest_ma is None:
        relation, direction = "20MA 資料不足", "均線方向資料不足"
    else:
        close = series.candles[-1].close
        relation = "價格在 20MA 上方" if close > latest_ma else "價格在 20MA 下方" if close < latest_ma else "價格位於 20MA"
        previous = next((value for value in reversed(ma_values[:-1]) if value is not None), None)
        direction = "均線上彎" if previous is not None and latest_ma > previous else "均線下彎" if previous is not None and latest_ma < previous else "均線走平"
    return f"{TIMEFRAME_LABELS[series.timeframe]}｜{relation}｜{direction}｜趨勢線資料不足｜支撐壓力資料不足｜量能僅顯示原始成交量"


def _chart_svg(series: ChartSeries, ma_values: tuple[float | None, ...]) -> str:
    candles, ma_values = series.candles[-80:], ma_values[-80:]
    if not candles:
        return "<div class='chart-empty' role='status'><strong>資料不足</strong><p>歷史 K 線來源尚未接入；系統不補假資料。</p></div>"
    top, bottom, left, right = 28.0, 330.0, 52.0, 980.0
    volume_top, volume_bottom = 350.0, 450.0
    high, low = max(item.high for item in candles), min(item.low for item in candles)
    span = high - low or 1.0
    # Keep sparse live series visually comparable with a normal chart.  Using
    # the candle count directly makes two or three early-session bars expand
    # into enormous blocks across the full viewport.
    visible_slots = max(len(candles), 20)
    step = (right - left) / visible_slots
    first_x = right - (len(candles) - 0.5) * step
    max_volume = max((item.volume for item in candles), default=0) or 1
    body_width = min(18.0, max(2.0, step * 0.58))
    y = lambda value: top + (high - value) / span * (bottom - top)
    bodies: list[str] = []
    volumes: list[str] = []
    for index, candle in enumerate(candles):
        x = first_x + index * step
        colour = "chart-up" if candle.close >= candle.open else "chart-down"
        body_top = min(y(candle.open), y(candle.close))
        body_height = max(1.5, abs(y(candle.open) - y(candle.close)))
        bodies.append(f"<g class='{colour}'><line x1='{x:.2f}' y1='{y(candle.high):.2f}' x2='{x:.2f}' y2='{y(candle.low):.2f}'/><rect x='{x-body_width/2:.2f}' y='{body_top:.2f}' width='{body_width:.2f}' height='{body_height:.2f}'/></g>")
        volume_height = candle.volume / max_volume * (volume_bottom - volume_top)
        volumes.append(f"<rect class='{colour}' x='{x-body_width/2:.2f}' y='{volume_bottom-volume_height:.2f}' width='{body_width:.2f}' height='{volume_height:.2f}'/>")
    points = [f"{first_x + index * step:.2f},{y(value):.2f}" for index, value in enumerate(ma_values) if value is not None]
    ma_line = f"<polyline class='chart-ma20' points='{' '.join(points)}'/>" if len(points) > 1 else ""
    return ("<svg class='candlestick-chart' viewBox='0 0 1024 480' role='img' aria-label='唯讀 K 線、20MA 與成交量'>"
            f"<text class='chart-price-label' x='8' y='{top+8:.0f}'>{high:,.2f}</text><text class='chart-price-label' x='8' y='{bottom:.0f}'>{low:,.2f}</text>"
            "<line class='chart-axis' x1='52' y1='330' x2='980' y2='330'/><line class='chart-axis' x1='52' y1='450' x2='980' y2='450'/>"
            f"<g class='chart-candles'>{''.join(bodies)}</g>{ma_line}<g class='chart-volumes'>{''.join(volumes)}</g></svg>")


def render_multi_timeframe_chart_html(source: ChartDataReadOnlySource = EMPTY_CHART_DATA_SOURCE, *, instrument: str = "TMF", timeframe: str = "60m") -> str:
    valid = instrument in {"TX", "MTX", "TMF"} and timeframe in SUPPORTED_CHART_TIMEFRAMES
    series = source.read_series(instrument, timeframe) if valid else ChartSeries(instrument, timeframe, (), "invalid-selection", None)
    ma_values = _ma20(series.candles)
    timeframe_tabs = "".join(f"<a class='chart-tab {'active' if item == timeframe else ''}' href='/charts?instrument={escape(instrument)}&timeframe={item}'>{TIMEFRAME_LABELS[item]}</a>" for item in SUPPORTED_CHART_TIMEFRAMES)
    instrument_tabs = "".join(f"<a class='chart-tab {'active' if item == instrument else ''}' href='/charts?instrument={item}&timeframe={escape(timeframe)}'>{item}</a>" for item in ("TX", "MTX", "TMF"))
    updated = series.updated_at.isoformat() if series.updated_at is not None else "—"
    status = _summary(series, ma_values) if valid else "商品或週期無效"
    return f"""<!doctype html><html class='chart-page' lang='zh-Hant-TW'><head><meta charset='utf-8'><title>KAM 多週期 K 線</title><link rel='stylesheet' href='/static/operator.css'></head><body class='chart-page'><main class='chart-main'>
      <header><div><h1>多週期 K 線</h1><small>60 分・日・週｜唯讀市場結構檢視</small></div><a class='account-chip' href='/'>返回市場儀表板</a><span>禁止真實下單</span></header>
      <nav class='chart-toolbar' aria-label='圖表商品與週期'>{instrument_tabs}<span class='chart-toolbar-divider'></span>{timeframe_tabs}</nav>
      <div class='chart-summary'>{escape(status)}</div><section class='chart-panel'>{_chart_svg(series, ma_values)}</section>
      <aside class='chart-overlays' aria-label='圖表顯示項目'><span class='enabled'>K 線</span><span class='enabled'>20MA</span><span>上升趨勢線｜尚未接入</span><span>下降趨勢線｜尚未接入</span><span>支撐壓力｜尚未接入</span><span class='enabled'>成交量</span></aside>
      <footer class='chart-footer'><span>資料來源：{escape(series.source)}</span><span>更新時間：{escape(updated)}</span><span>資料不足時不補假資料</span><span>任何單一指標均不構成進出場訊號</span></footer>
    </main></body></html>"""
