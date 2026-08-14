"""GET-only multi-timeframe chart read model and SVG renderer."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal
from html import escape
from math import isfinite
from typing import Protocol

SUPPORTED_CHART_TIMEFRAMES = ("15m", "60m", "1d", "1w")
TIMEFRAME_LABELS = {"15m": "15 分 K", "60m": "60 分 K", "1d": "日 K", "1w": "週 K"}


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
    current_price: float | None = None
    current_price_at: datetime | None = None
    last_candle_is_forming: bool = False
    forming_label: str | None = None

    def __post_init__(self) -> None:
        if self.current_price is not None and (
            not isfinite(self.current_price) or self.current_price <= 0
        ):
            raise ValueError("current_price must be finite and positive")
        if self.current_price_at is not None and (
            self.current_price_at.tzinfo is None or self.current_price_at.utcoffset() is None
        ):
            raise ValueError("current_price_at must be timezone-aware")
        if (self.current_price is None) != (self.current_price_at is None):
            raise ValueError("current price and timestamp must be supplied together")
        if self.last_candle_is_forming:
            if not self.candles or not self.forming_label:
                raise ValueError("forming series requires a candle and label")
        elif self.forming_label is not None:
            raise ValueError("forming label requires a forming candle")


@dataclass(frozen=True, slots=True)
class _ChartReferenceMetrics:
    current_price: float | None
    ma20: float | None
    resistance: float | None
    support: float | None
    range_window_bars: int


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


def _reference_metrics(
    series: ChartSeries,
    ma_values: tuple[float | None, ...],
) -> _ChartReferenceMetrics:
    current_price = series.current_price
    if current_price is None and series.candles:
        current_price = series.candles[-1].close
    reference_candles = (
        series.candles[:-1] if series.last_candle_is_forming else series.candles
    )
    range_window = reference_candles[-20:]
    if len(range_window) < 5:
        resistance = None
        support = None
    else:
        resistance = max(item.high for item in range_window)
        support = min(item.low for item in range_window)
    return _ChartReferenceMetrics(
        current_price=current_price,
        ma20=ma_values[-1] if ma_values else None,
        resistance=resistance,
        support=support,
        range_window_bars=len(range_window),
    )


def _price_text(value: float | None) -> str:
    if value is None:
        return "—"
    rounded = Decimal(str(value)).quantize(Decimal(1), rounding=ROUND_HALF_UP)
    return f"{int(rounded):,}"


def _ma_caption(
    metrics: _ChartReferenceMetrics,
    ma_values: tuple[float | None, ...],
) -> str:
    if metrics.ma20 is None:
        return "累積滿 20 根 K 棒後形成"
    relation = "現價在均線上方"
    if metrics.current_price is not None:
        if metrics.current_price < metrics.ma20:
            relation = "現價在均線下方"
        elif metrics.current_price == metrics.ma20:
            relation = "現價位於均線"
    previous = next((value for value in reversed(ma_values[:-1]) if value is not None), None)
    direction = "走平"
    if previous is not None:
        direction = (
            "上彎"
            if metrics.ma20 > previous
            else "下彎"
            if metrics.ma20 < previous
            else "走平"
        )
    return f"{relation}・均線{direction}"


def _range_caption(
    level: float | None,
    current_price: float | None,
    *,
    window_bars: int,
    resistance: bool,
) -> str:
    if level is None:
        return f"已完成 {window_bars}/5 根；資料仍不足"
    prefix = f"最近 {window_bars} 根已完成 K 棒"
    if current_price is None:
        return prefix
    distance = abs(level - current_price)
    if resistance:
        relation = (
            f"距現價 {distance:,.0f} 點"
            if level >= current_price
            else f"現價高於區間上緣 {distance:,.0f} 點"
        )
    else:
        relation = (
            f"距現價 {distance:,.0f} 點"
            if level <= current_price
            else f"現價低於區間下緣 {distance:,.0f} 點"
        )
    return f"{prefix}・{relation}"


def _price_board(
    series: ChartSeries,
    ma_values: tuple[float | None, ...],
) -> str:
    metrics = _reference_metrics(series, ma_values)
    current_label = (
        "即時微台"
        if series.current_price is not None and series.instrument == "TMF"
        else "即時價"
        if series.current_price is not None
        else "最新收盤"
    )
    current_caption = (
        "富邦即時報價・每 3 秒刷新"
        if series.current_price is not None
        else "目前以最新 K 棒收盤顯示"
    )
    ma_label = {
        "15m": "15 分 20MA",
        "60m": "60 分 20MA",
        "1d": "20 日線",
        "1w": "20 週線",
    }.get(series.timeframe, "20MA")
    resistance_caption = _range_caption(
        metrics.resistance,
        metrics.current_price,
        window_bars=metrics.range_window_bars,
        resistance=True,
    )
    support_caption = _range_caption(
        metrics.support,
        metrics.current_price,
        window_bars=metrics.range_window_bars,
        resistance=False,
    )
    return (
        "<div class='chart-price-board' aria-label='即時價位與區間參考'>"
        "<div class='chart-price-metric chart-price-current'>"
        f"<span>{current_label}</span><strong>{_price_text(metrics.current_price)}</strong>"
        f"<small>{current_caption}</small></div>"
        "<div class='chart-price-metric chart-price-ma'>"
        f"<span>{ma_label}</span><strong>{_price_text(metrics.ma20)}</strong>"
        f"<small>{_ma_caption(metrics, ma_values)}</small></div>"
        "<div class='chart-price-metric chart-price-resistance'>"
        f"<span>20 棒上壓力</span><strong>{_price_text(metrics.resistance)}</strong>"
        f"<small>{resistance_caption}</small></div>"
        "<div class='chart-price-metric chart-price-support'>"
        f"<span>20 棒下支撐</span><strong>{_price_text(metrics.support)}</strong>"
        f"<small>{support_caption}</small></div></div>"
        + (
            "<div class='chart-level-controls'><button id='chart-range-toggle' class='chart-overlay-toggle' type='button' aria-pressed='false'>顯示支撐／壓力＋趨勢線</button>"
            "<small>水平線＝最近上下緣・斜線＝最近有效波段高低點</small></div>"
            if metrics.resistance is not None and metrics.support is not None
            else "<div class='chart-level-controls'><button id='chart-range-toggle' class='chart-overlay-toggle' type='button' disabled>支撐壓力資料不足</button></div>"
        )
    )


def _summary(series: ChartSeries, ma_values: tuple[float | None, ...]) -> str:
    if not series.candles:
        return f"{TIMEFRAME_LABELS.get(series.timeframe, '週期無效')}｜資料不足"
    metrics = _reference_metrics(series, ma_values)
    range_status = (
        f"{metrics.range_window_bars} 棒支撐壓力已更新"
        if metrics.resistance is not None and metrics.support is not None
        else "支撐壓力資料不足"
    )
    latest_ma = ma_values[-1]
    if latest_ma is None:
        count = len(series.candles)
        missing = max(0, 20 - count)
        summary = (
            f"{TIMEFRAME_LABELS[series.timeframe]}｜已累積 {count}/20 根｜"
            f"尚缺 {missing} 根建立 20MA｜{range_status}｜資料持續自動累積"
        )
    else:
        close = metrics.current_price or series.candles[-1].close
        relation = (
            "價格在 20MA 上方"
            if close > latest_ma
            else "價格在 20MA 下方"
            if close < latest_ma
            else "價格位於 20MA"
        )
        previous = next((value for value in reversed(ma_values[:-1]) if value is not None), None)
        direction = (
            "均線上彎"
            if previous is not None and latest_ma > previous
            else "均線下彎"
            if previous is not None and latest_ma < previous
            else "均線走平"
        )
        summary = f"{TIMEFRAME_LABELS[series.timeframe]}｜{relation}｜{direction}｜趨勢線資料不足｜{range_status}｜量能僅顯示原始成交量"
    if series.last_candle_is_forming:
        return f"{summary}｜{series.forming_label}｜僅供顯示、不進入 KAM 或 Paper"
    return summary


def _time_label(value: datetime, timeframe: str) -> str:
    taiwan = timezone(timedelta(hours=8))
    pattern = "%Y/%m/%d" if timeframe in {"1d", "1w"} else "%m/%d %H:%M"
    return value.astimezone(taiwan).strftime(pattern)


def _recent_trend_anchors(
    series: ChartSeries,
) -> tuple[
    tuple[datetime, float, datetime, float] | None,
    tuple[datetime, float, datetime, float] | None,
]:
    """Return the latest rising-low and falling-high pivot pairs from closed bars."""
    completed = series.candles[:-1] if series.last_candle_is_forming else series.candles
    candles = completed[-80:]
    if len(candles) < 5:
        return None, None
    pivot_lows = [
        index
        for index in range(2, len(candles) - 2)
        if candles[index].low <= candles[index - 1].low
        and candles[index].low < candles[index - 2].low
        and candles[index].low <= candles[index + 1].low
        and candles[index].low < candles[index + 2].low
    ]
    pivot_highs = [
        index
        for index in range(2, len(candles) - 2)
        if candles[index].high >= candles[index - 1].high
        and candles[index].high > candles[index - 2].high
        and candles[index].high >= candles[index + 1].high
        and candles[index].high > candles[index + 2].high
    ]
    rising = next(
        (
            (candles[left].opened_at, candles[left].low, candles[right].opened_at, candles[right].low)
            for right in reversed(pivot_lows)
            for left in reversed([item for item in pivot_lows if item < right])
            if candles[right].low > candles[left].low
        ),
        None,
    )
    falling = next(
        (
            (candles[left].opened_at, candles[left].high, candles[right].opened_at, candles[right].high)
            for right in reversed(pivot_highs)
            for left in reversed([item for item in pivot_highs if item < right])
            if candles[right].high < candles[left].high
        ),
        None,
    )
    return rising, falling


def _chart_svg(series: ChartSeries, ma_values: tuple[float | None, ...]) -> str:
    metrics = _reference_metrics(series, ma_values)
    rising_anchors, falling_anchors = _recent_trend_anchors(series)
    candles, ma_values = series.candles[-80:], ma_values[-80:]
    if not candles:
        return "<div class='chart-empty' role='status'><strong>資料不足</strong><p>歷史 K 線來源尚未接入；系統不補假資料。</p></div>"
    top, bottom, left, right = 28.0, 270.0, 66.0, 980.0
    volume_top, volume_bottom = 292.0, 356.0
    displayed_price = (
        series.current_price if series.current_price is not None else candles[-1].close
    )
    raw_high = max(max(item.high for item in candles), displayed_price)
    raw_low = min(min(item.low for item in candles), displayed_price)
    raw_span = raw_high - raw_low or max(abs(raw_high) * 0.002, 1.0)
    high, low = raw_high + raw_span * 0.08, raw_low - raw_span * 0.08
    span = high - low
    # Keep sparse live series visually comparable with a normal chart.  Using
    # the candle count directly makes two or three early-session bars expand
    # into enormous blocks across the full viewport.
    # Use one compact visual rhythm for every timeframe.  Short series stay
    # grouped instead of stretching across the viewport; long series compress
    # only when the available plot width requires it.
    step = min(22.0, (right - left) / len(candles))
    first_x = (left + right) / 2 - (len(candles) - 1) * step / 2
    max_volume = max((item.volume for item in candles), default=0) or 1
    body_width = min(11.0, max(2.0, step * 0.52))

    def y(value: float) -> float:
        return top + (high - value) / span * (bottom - top)

    bodies: list[str] = []
    volumes: list[str] = []
    hover_zones: list[str] = []
    ma_label = {
        "15m": "20MA（15 分）",
        "60m": "20MA（60 分）",
        "1d": "20 日線",
        "1w": "20 週線",
    }[series.timeframe]
    for index, candle in enumerate(candles):
        x = first_x + index * step
        colour = "chart-up" if candle.close >= candle.open else "chart-down"
        forming = (
            " chart-forming"
            if (series.last_candle_is_forming and index == len(candles) - 1)
            else ""
        )
        body_top = min(y(candle.open), y(candle.close))
        body_height = max(1.5, abs(y(candle.open) - y(candle.close)))
        bodies.append(
            f"<g class='{colour}{forming}'><line x1='{x:.2f}' y1='{y(candle.high):.2f}' x2='{x:.2f}' y2='{y(candle.low):.2f}'/><rect x='{x - body_width / 2:.2f}' y='{body_top:.2f}' width='{body_width:.2f}' height='{body_height:.2f}'/></g>"
        )
        volume_height = candle.volume / max_volume * (volume_bottom - volume_top)
        volumes.append(
            f"<rect class='{colour}{forming}' x='{x - body_width / 2:.2f}' y='{volume_bottom - volume_height:.2f}' width='{body_width:.2f}' height='{volume_height:.2f}'/>"
        )
        ma_value = ma_values[index]
        timestamp = _time_label(candle.opened_at, series.timeframe)
        forming_state = (
            "true" if (series.last_candle_is_forming and index == len(candles) - 1) else "false"
        )
        accessible_ma = (
            f"{ma_label} {ma_value:,.2f}" if ma_value is not None else f"{ma_label} 尚未形成"
        )
        hover_zones.append(
            f"<rect class='chart-hover-zone' tabindex='0' x='{x - step / 2:.2f}' y='{top:.2f}' width='{step:.2f}' height='{volume_bottom - top:.2f}' "
            f"data-x='{x:.2f}' data-time='{timestamp}' data-open='{candle.open:.10g}' data-high='{candle.high:.10g}' "
            f"data-low='{candle.low:.10g}' data-close='{candle.close:.10g}' data-volume='{candle.volume}' "
            f"data-ma20='{'' if ma_value is None else f'{ma_value:.10g}'}' data-ma-label='{ma_label}' data-forming='{forming_state}' "
            f"aria-label='{timestamp}，開盤 {candle.open:,.2f}，最高 {candle.high:,.2f}，最低 {candle.low:,.2f}，收盤 {candle.close:,.2f}，{accessible_ma}'/>"
        )
    points = [
        f"{first_x + index * step:.2f},{y(value):.2f}"
        for index, value in enumerate(ma_values)
        if value is not None
    ]
    ma_line = (
        f"<polyline class='chart-ma20' points='{' '.join(points)}'/>" if len(points) > 1 else ""
    )
    grid_values = tuple(low + span * index / 4 for index in range(5))
    grid = "".join(
        f"<line class='chart-grid' x1='{left:.0f}' y1='{y(value):.2f}' x2='{right:.0f}' y2='{y(value):.2f}'/>"
        f"<text class='chart-price-label' x='8' y='{y(value) + 4:.2f}'>{value:,.0f}</text>"
        for value in reversed(grid_values)
    )
    latest = candles[-1]
    latest_y = y(displayed_price)
    range_lines = ""
    if metrics.resistance is not None and metrics.support is not None:
        resistance_y = y(metrics.resistance)
        support_y = y(metrics.support)
        range_lines = (
            "<g class='chart-range-lines' hidden>"
            f"<line class='chart-resistance-line' x1='{left:.0f}' y1='{resistance_y:.2f}' x2='{right:.0f}' y2='{resistance_y:.2f}'/>"
            f"<text class='chart-resistance-label' x='{right - 4:.0f}' y='{resistance_y - 5:.2f}' text-anchor='end'>上壓 {_price_text(metrics.resistance)}</text>"
            f"<line class='chart-support-line' x1='{left:.0f}' y1='{support_y:.2f}' x2='{right:.0f}' y2='{support_y:.2f}'/>"
            f"<text class='chart-support-label' x='{right - 4:.0f}' y='{support_y - 5:.2f}' text-anchor='end'>下撐 {_price_text(metrics.support)}</text>"
        )
        candle_indexes = {item.opened_at: index for index, item in enumerate(candles)}
        trend_parts: list[str] = []
        for anchors, line_class, label in (
            (rising_anchors, "chart-rising-trend-line", "上升趨勢"),
            (falling_anchors, "chart-falling-trend-line", "下降趨勢"),
        ):
            if anchors is None:
                continue
            first_time, first_price, second_time, second_price = anchors
            first_index = candle_indexes.get(first_time)
            second_index = candle_indexes.get(second_time)
            if first_index is None or second_index is None or first_index == second_index:
                continue
            slope = (second_price - first_price) / (second_index - first_index)
            projected_price = second_price + slope * (len(candles) - 1 - second_index)
            trend_parts.append(
                f"<line class='{line_class}' x1='{first_x + first_index * step:.2f}' y1='{y(first_price):.2f}' x2='{first_x + (len(candles) - 1) * step:.2f}' y2='{y(projected_price):.2f}'/>"
                f"<text class='{line_class}-label' x='{first_x + (len(candles) - 1) * step - 4:.2f}' y='{y(projected_price) - 5:.2f}' text-anchor='end'>{label}</text>"
            )
        range_lines += "".join(trend_parts) + "</g>"
    time_labels = (
        f"<text class='chart-time-label' x='{first_x:.2f}' y='378' text-anchor='start'>{_time_label(candles[0].opened_at, series.timeframe)}</text>"
        f"<text class='chart-time-label' x='{first_x + (len(candles) - 1) * step:.2f}' y='378' text-anchor='end'>{_time_label(latest.opened_at, series.timeframe)}</text>"
    )
    return (
        "<svg class='candlestick-chart' viewBox='0 0 1024 392' role='img' aria-label='唯讀 K 線、20MA、即時水平線與成交量'>"
        f"{grid}<line class='chart-current-line' x1='{left:.0f}' y1='{latest_y:.2f}' x2='{right:.0f}' y2='{latest_y:.2f}'/>"
        f"<g class='chart-candles'>{''.join(bodies)}</g>{ma_line}{range_lines}<g class='chart-volumes'>{''.join(volumes)}</g>"
        f"<text class='chart-volume-label' x='{left:.0f}' y='288'>成交量</text>{time_labels}"
        f"<g class='chart-crosshair' hidden><line class='chart-crosshair-x' x1='0' y1='{top:.2f}' x2='0' y2='{volume_bottom:.2f}'/><line class='chart-crosshair-y' x1='{left:.2f}' y1='0' x2='{right:.2f}' y2='0'/></g>"
        f"<g class='chart-hover-zones'>{''.join(hover_zones)}</g></svg>"
    )


def render_multi_timeframe_chart_html(
    source: ChartDataReadOnlySource = EMPTY_CHART_DATA_SOURCE,
    *,
    instrument: str = "TMF",
    timeframe: str = "60m",
) -> str:
    valid = instrument in {"TX", "MTX", "TMF"} and timeframe in SUPPORTED_CHART_TIMEFRAMES
    series = (
        source.read_series(instrument, timeframe)
        if valid
        else ChartSeries(instrument, timeframe, (), "invalid-selection", None)
    )
    ma_values = _ma20(series.candles)
    timeframe_tabs = "".join(
        f"<a class='chart-tab {'active' if item == timeframe else ''}' href='/charts?instrument={escape(instrument)}&timeframe={item}'>{TIMEFRAME_LABELS[item]}</a>"
        for item in SUPPORTED_CHART_TIMEFRAMES
    )
    instrument_tabs = "".join(
        f"<a class='chart-tab {'active' if item == instrument else ''}' href='/charts?instrument={item}&timeframe={escape(timeframe)}'>{item}</a>"
        for item in ("TX", "MTX", "TMF")
    )
    updated = series.updated_at.isoformat() if series.updated_at is not None else "—"
    quote_updated = (
        series.current_price_at.isoformat() if series.current_price_at is not None else "—"
    )
    status = _summary(series, ma_values) if valid else "商品或週期無效"
    metrics = _reference_metrics(series, ma_values)
    range_overlay = (
        "<span class='enabled'>20 棒壓力／支撐</span>"
        if metrics.resistance is not None and metrics.support is not None
        else "<span>支撐壓力｜資料不足</span>"
    )
    return f"""<!doctype html><html class='chart-page' lang='zh-Hant-TW'><head><meta charset='utf-8'><title>KAM 多週期 K 線</title><link rel='stylesheet' href='/static/operator.css'><script src='/static/chart-refresh.js' defer></script></head><body class='chart-page'><main class='chart-main'>
      <header><div><h1>多週期 K 線</h1><small>15 分・60 分・日・週｜唯讀市場結構檢視</small></div><a class='account-chip' href='/'>返回市場儀表板</a><span id='chart-live-status' class='chart-live-status' role='status' aria-live='polite'>每 3 秒更新・禁止真實下單</span></header>
      <nav class='chart-toolbar' aria-label='圖表商品與週期'>{instrument_tabs}<span class='chart-toolbar-divider'></span>{timeframe_tabs}</nav>
      <div id='chart-summary' class='chart-summary'>{escape(status)}</div><section id='chart-panel' class='chart-panel'>{_price_board(series, ma_values)}{_chart_svg(series, ma_values)}<div class='chart-tooltip' role='status' aria-live='polite' hidden></div></section>
      <aside class='chart-overlays' aria-label='圖表顯示項目'><span class='enabled'>K 線</span><span class='enabled'>20MA</span><span>上升趨勢線｜尚未接入</span><span>下降趨勢線｜尚未接入</span>{range_overlay}<span class='enabled'>成交量</span></aside>
      <footer id='chart-footer' class='chart-footer'><span>資料來源：{escape(series.source)}</span><span>K 線時間：{escape(updated)}</span><span>即時報價時間：{escape(quote_updated)}</span><span>資料不足時不補假資料</span><span>任何單一指標均不構成進出場訊號</span></footer>
    </main></body></html>"""
