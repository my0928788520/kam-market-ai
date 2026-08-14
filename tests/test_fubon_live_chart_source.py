from datetime import UTC, datetime, timedelta
from types import MappingProxyType

from kam_market_ai.market_data.fubon_five_timeframe_pipeline import (
    FiveTimeframe,
    FiveTimeframeCandleResult,
)
from kam_market_ai.market_data.fubon_live_chart_source import FubonLiveChartSource
from kam_market_ai.models import Candle, Instrument


def result() -> FiveTimeframeCandleResult:
    start = datetime(2026, 8, 14, 0, 45, tzinfo=UTC)
    values = tuple(
        Candle(Instrument.TMF, start + timedelta(hours=index), start + timedelta(hours=index + 1), 100 + index, 103 + index, 99 + index, 102 + index, 10 + index)
        for index in range(3)
    )
    return FiveTimeframeCandleResult(
        Instrument.TMF,
        None,
        MappingProxyType({
            FiveTimeframe.M5: values,
            FiveTimeframe.M15: values,
            FiveTimeframe.M60: values,
        }),
        (FiveTimeframe.DAY, FiveTimeframe.WEEK),
        3,
    )


def test_live_chart_exposes_verified_60m_candles_in_memory() -> None:
    source = FubonLiveChartSource(result)
    series = source.read_series("TMF", "60m")

    assert len(series.candles) == 3
    assert series.candles[-1].close == 104
    assert series.source == "fubon-live:verified-candles"
    assert series.updated_at == datetime(2026, 8, 14, 3, 45, tzinfo=UTC)


def test_live_chart_keeps_unverified_day_and_week_empty() -> None:
    source = FubonLiveChartSource(result)

    assert source.read_series("TMF", "1d").candles == ()
    assert source.read_series("TMF", "1w").candles == ()
    assert source.read_series("TX", "60m").candles == ()


def test_live_chart_accumulates_normalized_history_across_restarts(tmp_path) -> None:
    history = tmp_path / "tmf_60m.json"
    FubonLiveChartSource(result, history_path=history).capture_latest()
    start = datetime(2026, 8, 14, 3, 45, tzinfo=UTC)
    newest = Candle(Instrument.TMF, start, start + timedelta(hours=1), 104, 106, 103, 105, 20)
    second = FiveTimeframeCandleResult(
        Instrument.TMF,
        None,
        MappingProxyType({
            FiveTimeframe.M5: (newest,),
            FiveTimeframe.M15: (newest,),
            FiveTimeframe.M60: (newest,),
        }),
        (FiveTimeframe.DAY, FiveTimeframe.WEEK),
        3,
    )
    source = FubonLiveChartSource(lambda: second, history_path=history)
    series = source.read_series("TMF", "60m")

    assert len(series.candles) == 4
    assert [item.opened_at for item in series.candles] == sorted(item.opened_at for item in series.candles)
    assert series.source == "fubon-live:normalized-local-history"
    assert "kam-normalized-chart-history-v1" in history.read_text(encoding="utf-8")


def test_corrupt_local_history_fails_closed_to_current_verified_data(tmp_path) -> None:
    history = tmp_path / "tmf_60m.json"
    history.write_text("not-json", encoding="utf-8")
    source = FubonLiveChartSource(result, history_path=history)

    series = source.read_series("TMF", "60m")

    assert len(series.candles) == 3
    assert series.source == "fubon-live:normalized-local-history"
