from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from kam_market_ai.paper_trading.historical_chart_source import (
    ExportedHistoricalChartSource, load_exported_historical_chart_source,
)
from kam_market_ai.paper_trading.multi_timeframe_chart import render_multi_timeframe_chart_html

NOW = datetime(2026, 8, 10, 8, tzinfo=timezone.utc)


def row(index: int = 0, **changes: object) -> dict[str, object]:
    opened = NOW - timedelta(hours=25 - index)
    value: dict[str, object] = {
        "instrument": "MTX", "timeframe": "60m",
        "opened_at": opened.isoformat(), "closed_at": (opened + timedelta(hours=1)).isoformat(),
        "open": str(22000 + index), "high": str(22010 + index),
        "low": str(21990 + index), "close": str(22005 + index),
        "volume": str(100 + index), "source_record_id": f"mtx-60m-{index:03d}",
        "closed": True,
    }
    value.update(changes)
    return value


def source(rows: tuple[dict[str, object], ...]) -> ExportedHistoricalChartSource:
    return ExportedHistoricalChartSource(rows, "fubon-export", "2026-08-10", NOW)


def test_exported_history_renders_validated_bars_with_traceable_source() -> None:
    selected = source(tuple(row(index) for index in range(24)))
    series = selected.read_series("MTX", "60m")
    assert len(series.candles) == 24
    assert series.source.startswith("fubon-export@2026-08-10｜")
    html = render_multi_timeframe_chart_html(selected, instrument="MTX", timeframe="60m")
    assert "<svg class='candlestick-chart'" in html
    assert "價格在 20MA 上方" in html


@pytest.mark.parametrize("rows", [
    (row(closed=False),),
    (row(high="1"),),
    (row(closed_at=(NOW + timedelta(days=1)).isoformat()),),
])
def test_invalid_or_future_history_fails_closed(rows: tuple[dict[str, object], ...]) -> None:
    series = source(rows).read_series("MTX", "60m")
    assert series.candles == ()
    assert "blocked" in series.source


def test_loader_requires_bounded_versioned_json_export(tmp_path) -> None:
    path = tmp_path / "history.json"
    path.write_text(json.dumps({
        "dataset_id": "official-export", "dataset_version": "v1",
        "captured_at": NOW.isoformat(), "bars": [row()],
    }), encoding="utf-8")
    loaded = load_exported_historical_chart_source(path)
    assert loaded.dataset_id == "official-export"
    assert len(loaded.read_series("MTX", "60m").candles) == 1
    path.write_text("[]", encoding="utf-8")
    with pytest.raises(ValueError, match="CHART_HISTORY_ROOT_INVALID"):
        load_exported_historical_chart_source(path)
