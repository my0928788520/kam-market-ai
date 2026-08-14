from datetime import UTC, date, datetime, time, timedelta
from types import MappingProxyType
from zoneinfo import ZoneInfo

from kam_market_ai.market_data.fubon_five_timeframe_pipeline import (
    FiveTimeframe,
    FiveTimeframeCandleResult,
)
from kam_market_ai.market_data.fubon_live_chart_source import (
    FubonLiveChartSource,
    FubonLiveQuoteSource,
    LiveChartPrice,
)
from kam_market_ai.market_data.fubon_neo import AuthorizedMarketDataClients
from kam_market_ai.models import Candle, Instrument
from kam_market_ai.paper_trading.multi_timeframe_chart import ChartCandle

TAIPEI = ZoneInfo("Asia/Taipei")


class WebSocket:
    def on(self, *_args):
        pass

    def off(self, *_args):
        pass

    def connect(self):
        pass

    def subscribe(self, *_args):
        pass

    def unsubscribe(self, *_args):
        pass

    def disconnect(self):
        pass


class IntradayQuote:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []
        self.symbol = "TMFH6"
        self.price = 45839
        self.observed_at = datetime(2026, 8, 14, 5, 30, tzinfo=UTC)

    def quote(self, **params: object) -> dict[str, object]:
        self.calls.append(dict(params))
        return {
            "symbol": self.symbol,
            "lastTrade": {
                "price": self.price,
                "time": int(self.observed_at.timestamp() * 1_000_000),
            },
        }


class Rest:
    def __init__(self, intraday: object) -> None:
        self.intraday = intraday
        self.historical = object()


def quote_clients() -> tuple[AuthorizedMarketDataClients, IntradayQuote]:
    intraday = IntradayQuote()
    clients = AuthorizedMarketDataClients(
        WebSocket(),
        Rest(intraday),
        WebSocket(),
        Rest(IntradayQuote()),
    )
    return clients, intraday


def result() -> FiveTimeframeCandleResult:
    start = datetime(2026, 8, 14, 0, 45, tzinfo=UTC)
    values = tuple(
        Candle(
            Instrument.TMF,
            start + timedelta(hours=index),
            start + timedelta(hours=index + 1),
            100 + index,
            103 + index,
            99 + index,
            102 + index,
            10 + index,
        )
        for index in range(3)
    )
    return FiveTimeframeCandleResult(
        Instrument.TMF,
        None,
        MappingProxyType(
            {
                FiveTimeframe.M5: values,
                FiveTimeframe.M15: values,
                FiveTimeframe.M60: values,
            }
        ),
        (FiveTimeframe.DAY, FiveTimeframe.WEEK),
        3,
    )


def closed_higher_timeframes() -> MappingProxyType:
    days = []
    first = date(2026, 7, 13)
    for index in range(32):
        trading_date = first + timedelta(days=index)
        if trading_date.weekday() >= 5 or trading_date >= date(2026, 8, 14):
            continue
        opened = datetime.combine(trading_date, time.min, TAIPEI).astimezone(UTC)
        days.append(
            Candle(
                Instrument.TMF,
                opened,
                opened + timedelta(days=1),
                90 + index,
                93 + index,
                89 + index,
                92 + index,
                100 + index,
            )
        )
    weeks = []
    for week_start in (date(2026, 7, 13), date(2026, 7, 20), date(2026, 7, 27), date(2026, 8, 3)):
        opened = datetime.combine(week_start, time.min, TAIPEI).astimezone(UTC)
        weeks.append(
            Candle(
                Instrument.TMF,
                opened,
                opened + timedelta(days=7),
                90,
                120,
                88,
                115,
                500,
            )
        )
    return MappingProxyType(
        {
            FiveTimeframe.DAY: tuple(days),
            FiveTimeframe.WEEK: tuple(weeks),
        }
    )


def test_live_chart_exposes_verified_60m_candles_in_memory() -> None:
    source = FubonLiveChartSource(result)
    series = source.read_series("TMF", "60m")

    assert len(series.candles) == 3
    assert series.candles[-1].close == 104
    assert series.source == "fubon-live:verified-candles"
    assert series.updated_at == datetime(2026, 8, 14, 3, 45, tzinfo=UTC)


def test_live_chart_exposes_and_accumulates_verified_15m_candles(tmp_path) -> None:
    history = tmp_path / "tmf_15m.json"
    source = FubonLiveChartSource(result, history_15m_path=history)

    series = source.read_series("TMF", "15m")

    assert len(series.candles) == 3
    assert series.source == "fubon-live:normalized-local-history"
    assert '"timeframe": "15m"' in history.read_text(encoding="utf-8")


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
        MappingProxyType(
            {
                FiveTimeframe.M5: (newest,),
                FiveTimeframe.M15: (newest,),
                FiveTimeframe.M60: (newest,),
            }
        ),
        (FiveTimeframe.DAY, FiveTimeframe.WEEK),
        3,
    )
    source = FubonLiveChartSource(lambda: second, history_path=history)
    series = source.read_series("TMF", "60m")

    assert len(series.candles) == 4
    assert [item.opened_at for item in series.candles] == sorted(
        item.opened_at for item in series.candles
    )
    assert series.source == "fubon-live:normalized-local-history"
    assert "kam-normalized-chart-history-v1" in history.read_text(encoding="utf-8")


def test_corrupt_local_history_fails_closed_to_current_verified_data(tmp_path) -> None:
    history = tmp_path / "tmf_60m.json"
    history.write_text("not-json", encoding="utf-8")
    source = FubonLiveChartSource(result, history_path=history)

    series = source.read_series("TMF", "60m")

    assert len(series.candles) == 3
    assert series.source == "fubon-live:normalized-local-history"


def test_live_quote_source_normalizes_last_trade_without_retaining_payload() -> None:
    clients, intraday = quote_clients()
    source = FubonLiveQuoteSource(clients, symbol="TMFH6")

    first = source.refresh()
    intraday.price = 45842
    intraday.observed_at += timedelta(seconds=3)
    second = source.refresh()

    assert first.price == 45839
    assert second.price == 45842
    assert second.observed_at == datetime(2026, 8, 14, 5, 30, 3, tzinfo=UTC)
    assert intraday.calls == [{"symbol": "TMFH6"}, {"symbol": "TMFH6"}]
    assert not hasattr(second, "raw_payload")


def test_after_hours_quote_uses_official_session_and_bad_identity_keeps_last_good() -> None:
    clients, intraday = quote_clients()
    source = FubonLiveQuoteSource(clients, symbol="TMFH6", after_hours=True)
    assert source.refresh_safely() is True
    good = source.latest

    intraday.symbol = "TMFI6"

    assert source.refresh_safely() is False
    assert source.latest == good
    assert intraday.calls == [
        {"symbol": "TMFH6", "session": "afterhours"},
        {"symbol": "TMFH6", "session": "afterhours"},
    ]


def test_chart_series_overlays_live_quote_but_keeps_verified_candle_history() -> None:
    current = LiveChartPrice(
        "TMF",
        "TMFH6",
        45839,
        datetime(2026, 8, 14, 5, 30, tzinfo=UTC),
    )
    source = FubonLiveChartSource(
        result,
        current_price_provider=lambda: current,
    )

    series = source.read_series("TMF", "60m")

    assert len(series.candles) == 3
    assert series.candles[-1].close == 104
    assert series.current_price == 45839
    assert series.current_price_at == current.observed_at
    assert series.source.endswith("+fubon-live-quote")


def test_regular_session_appends_chart_only_forming_day_and_week() -> None:
    current = LiveChartPrice(
        "TMF",
        "TMFH6",
        105,
        datetime(2026, 8, 14, 5, 30, tzinfo=UTC),
    )
    source = FubonLiveChartSource(
        result,
        current_price_provider=lambda: current,
        closed_higher_timeframe_provider=closed_higher_timeframes,
    )

    daily = source.read_series("TMF", "1d")
    weekly = source.read_series("TMF", "1w")

    assert daily.last_candle_is_forming is True
    assert daily.forming_label == "本日形成中"
    assert daily.candles[-1] == ChartCandle(
        datetime(2026, 8, 13, 16, tzinfo=UTC),
        100,
        105,
        99,
        105,
        33,
    )
    assert weekly.last_candle_is_forming is True
    assert weekly.forming_label == "本週形成中"
    assert weekly.candles[-1].opened_at == datetime(2026, 8, 9, 16, tzinfo=UTC)
    assert daily.source.endswith("provisional-regular+fubon-live-quote")


def test_after_hours_forming_day_uses_next_weekday_without_upgrading_kam_data() -> None:
    start = datetime(2026, 8, 14, 7, tzinfo=UTC)  # Friday 15:00 in Taipei.
    values = tuple(
        Candle(
            Instrument.TMF,
            start + timedelta(minutes=15 * index),
            start + timedelta(minutes=15 * (index + 1)),
            100 + index,
            103 + index,
            99 + index,
            102 + index,
            10 + index,
        )
        for index in range(3)
    )
    partial = FiveTimeframeCandleResult(
        Instrument.TMF,
        "afterhours",
        MappingProxyType(
            {
                FiveTimeframe.M5: values,
                FiveTimeframe.M15: values,
                FiveTimeframe.M60: values,
            }
        ),
        (FiveTimeframe.DAY, FiveTimeframe.WEEK),
        3,
    )
    current = LiveChartPrice(
        "TMF",
        "TMFH6",
        106,
        datetime(2026, 8, 14, 7, 40, tzinfo=UTC),
    )
    source = FubonLiveChartSource(
        lambda: partial,
        current_price_provider=lambda: current,
        closed_higher_timeframe_provider=closed_higher_timeframes,
        after_hours=True,
    )

    daily = source.read_series("TMF", "1d")
    weekly = source.read_series("TMF", "1w")

    assert partial.missing_timeframes == (FiveTimeframe.DAY, FiveTimeframe.WEEK)
    assert daily.candles[-1].opened_at.astimezone(TAIPEI).date() == date(2026, 8, 17)
    assert weekly.candles[-1].opened_at.astimezone(TAIPEI).date() == date(2026, 8, 17)
    assert daily.source.endswith("provisional-night+fubon-live-quote")
    assert daily.last_candle_is_forming and weekly.last_candle_is_forming
