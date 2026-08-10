from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import pytest

from kam_market_ai.market_data.historical_chart_export import (
    CHART_HISTORY_EXPORT_VERSION,
    HistoricalChartExportPlan,
    build_historical_chart_export,
    write_historical_chart_export,
)
from kam_market_ai.models import Candle, Instrument
from kam_market_ai.paper_trading.historical_chart_source import (
    load_exported_historical_chart_source,
)

NOW = datetime(2026, 8, 10, 8, tzinfo=UTC)


class Provider:
    def __init__(self, *, invalid: str | None = None) -> None:
        self.calls: list[tuple[Instrument, int]] = []
        self.invalid = invalid

    async def historical_candles(self, instrument, start, end, interval_minutes):
        self.calls.append((instrument, interval_minutes))
        candle_end = start + timedelta(minutes=interval_minutes)
        candle = Candle(instrument, start, candle_end, 100.0, 110.0, 90.0, 105.0, 7)
        if self.invalid == "ohlc":
            candle = Candle(instrument, start, candle_end, 100.0, 95.0, 90.0, 105.0, 7)
        if self.invalid == "empty":
            return []
        return [candle]


def plan() -> HistoricalChartExportPlan:
    return HistoricalChartExportPlan(
        (Instrument.MTX, Instrument.TX),
        ("60m", "1d", "1w"),
        NOW - timedelta(days=8),
        NOW - timedelta(days=1),
        NOW,
        "fubon-official-export",
        "2026-08-10",
    )


def test_export_is_deterministic_traceable_and_consumable(tmp_path) -> None:
    provider = Provider()
    payload = asyncio.run(build_historical_chart_export(provider, plan()))
    assert payload["export_version"] == CHART_HISTORY_EXPORT_VERSION
    assert len(payload["bars"]) == 6
    assert len(payload["bars_sha256"]) == 64
    assert provider.calls == [
        (Instrument.MTX, 60),
        (Instrument.MTX, 1440),
        (Instrument.MTX, 10080),
        (Instrument.TX, 60),
        (Instrument.TX, 1440),
        (Instrument.TX, 10080),
    ]
    path = write_historical_chart_export((tmp_path / "history.json").resolve(), payload)
    loaded = load_exported_historical_chart_source(path)
    assert len(loaded.read_series("MTX", "60m").candles) == 1


@pytest.mark.parametrize(
    "invalid,code",
    [
        ("empty", "HISTORY_EXPORT_EMPTY_SERIES"),
        ("ohlc", "HISTORY_EXPORT_OHLCV_INVALID"),
    ],
)
def test_export_fails_closed_on_incomplete_or_invalid_series(invalid, code) -> None:
    with pytest.raises(ValueError, match=code):
        asyncio.run(build_historical_chart_export(Provider(invalid=invalid), plan()))


def test_plan_rejects_unverified_timeframes_and_future_ranges() -> None:
    with pytest.raises(ValueError, match="60m, 1d, and 1w"):
        HistoricalChartExportPlan(
            (Instrument.MTX,), ("15m",), NOW, NOW + timedelta(days=1), NOW, "x", "v1"
        )
    with pytest.raises(ValueError, match="not in the future"):
        HistoricalChartExportPlan(
            (Instrument.MTX,), ("60m",), NOW, NOW + timedelta(days=1), NOW, "x", "v1"
        )


def test_writer_refuses_relative_or_existing_path(tmp_path) -> None:
    with pytest.raises(ValueError, match="MUST_BE_ABSOLUTE"):
        write_historical_chart_export("history.json", {})
    path = (tmp_path / "history.json").resolve()
    path.write_text("do-not-replace", encoding="utf-8")
    with pytest.raises(FileExistsError, match="ALREADY_EXISTS"):
        write_historical_chart_export(path, {})
    assert path.read_text(encoding="utf-8") == "do-not-replace"
