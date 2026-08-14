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
