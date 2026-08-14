import csv
from datetime import UTC, date, datetime, timedelta
from io import BytesIO, StringIO
from pathlib import Path
from urllib.parse import parse_qs
from zipfile import ZIP_DEFLATED, ZipFile

import pytest

from kam_market_ai.market_data.fubon_five_timeframe_pipeline import (
    FubonFiveTimeframeCandlePipeline,
)
from kam_market_ai.market_data.fubon_live_five_timeframe_verifier import (
    FubonLiveFiveTimeframeVerifier,
)
from kam_market_ai.market_data.fubon_neo import (
    AuthorizedMarketDataClients,
    FubonIntradayCandlesAdapter,
    ResolvedFuturesContract,
    VerifiedContractResolver,
)
from kam_market_ai.market_data.taifex_official_history import (
    TAIFEX_DAILY_DOWNLOAD_URL,
    TAIFEX_INTRADAY_LIST_URL,
    TAIFEX_INTRADAY_PREFIX,
    TaifexOfficialHistoryError,
    TaifexOfficialHistorySource,
)
from kam_market_ai.models import Instrument


class WebSocket:
    def on(self, *_args): pass
    def off(self, *_args): pass
    def connect(self): pass
    def subscribe(self, *_args): pass
    def unsubscribe(self, *_args): pass
    def disconnect(self): pass


class Intraday:
    def candles(self, **params):
        return {
            "symbol": params["symbol"],
            "timeframe": params["timeframe"],
            "data": [
                {
                    "date": "2026-08-20T09:00:00+08:00",
                    "open": 22000,
                    "high": 22010,
                    "low": 21990,
                    "close": 22005,
                    "volume": 10,
                },
                {
                    "date": "2026-08-20T10:00:00+08:00",
                    "open": 22005,
                    "high": 22020,
                    "low": 22000,
                    "close": 22015,
                    "volume": 12,
                },
            ],
        }


class Rest:
    def __init__(self) -> None:
        self.intraday = Intraday()
        self.historical = object()


def _daily_csv(local_date: date) -> bytes:
    output = StringIO(newline="")
    rows = csv.writer(output, lineterminator="\r\n")
    rows.writerow([
        "交易日期", "契約", "到期月份(週別)", "開盤價", "最高價", "最低價", "收盤價",
        "漲跌價", "漲跌%", "成交量", "結算價", "未沖銷契約數", "最後最佳買價",
        "最後最佳賣價", "歷史最高價", "歷史最低價", "是否因訊息面暫停交易",
        "交易時段", "價差對單式委託成交量",
    ])
    first = local_date - timedelta(weeks=45)
    for index in range(45):
        trading_date = first + timedelta(weeks=index)
        base = 20000 + index * 10
        for contract, volume in (("202608", 1000), ("202609", 100)):
            rows.writerow([
                trading_date.strftime("%Y/%m/%d"), "TMF", contract, base, base + 30,
                base - 20, base + 10, 0, "0%", volume, base + 10, 1, base + 9,
                base + 11, base + 100, base - 100, "", "一般", "",
            ])
        rows.writerow([
            trading_date.strftime("%Y/%m/%d"), "TMF", "202608", base + 5,
            base + 35, base - 25, base + 15, 0, "0%", 2000, "-", "-", base + 14,
            base + 16, base + 100, base - 100, "", "盤後", "",
        ])
    return output.getvalue().encode("cp950")


def _intraday_zip(trading_date: date) -> bytes:
    output = StringIO(newline="")
    rows = csv.writer(output, lineterminator="\r\n")
    rows.writerow([
        "成交日期", "商品代號", "到期月份(週別)", "成交時間", "成交價格",
        "成交數量(B+S)", "近月價格", "遠月價格", "開盤集合競價 ",
    ])
    start = datetime.combine(trading_date, datetime.min.time()).replace(hour=8, minute=45)
    for index in range(61):
        observed = start + timedelta(minutes=5 * index)
        rows.writerow([
            trading_date.strftime("%Y%m%d"), "TMF    ", "202608     ",
            observed.strftime("%H%M%S"), str(22000 + index), "10", "-", "-", "",
        ])
    rows.writerow([
        trading_date.strftime("%Y%m%d"), "TMF    ", "202609     ", "090000",
        "22100", "1", "-", "-", "",
    ])
    archive = BytesIO()
    with ZipFile(archive, "w", ZIP_DEFLATED) as target:
        target.writestr(
            f"Daily_{trading_date.strftime('%Y_%m_%d')}.csv",
            output.getvalue().encode("cp950"),
        )
    return archive.getvalue()


class FixtureTransport:
    def __init__(self, local_date: date) -> None:
        self.local_date = local_date
        self.calls: list[tuple[str, bytes | None]] = []
        self.trading_dates = tuple(
            local_date - timedelta(days=offset)
            for offset in range(18, 0, -1)
            if (local_date - timedelta(days=offset)).weekday() < 5
        )[-12:]
        self.daily = _daily_csv(local_date)
        self.zips = {item: _intraday_zip(item) for item in self.trading_dates}

    def __call__(self, url: str, data: bytes | None, _maximum: int) -> bytes:
        self.calls.append((url, data))
        if url == TAIFEX_DAILY_DOWNLOAD_URL:
            values = parse_qs((data or b"").decode("ascii"))
            assert values["commodity_id"] == ["TMF"]
            assert values["down_type"] == ["1"]
            return self.daily
        if url == TAIFEX_INTRADAY_LIST_URL:
            return "\n".join(
                f"onclick=\"window.open('{TAIFEX_INTRADAY_PREFIX}"
                f"Daily_{item.strftime('%Y_%m_%d')}.zip')\""
                for item in self.trading_dates
            ).encode()
        for trading_date, payload in self.zips.items():
            if url.endswith(f"Daily_{trading_date.strftime('%Y_%m_%d')}.zip"):
                return payload
        raise AssertionError(url)


def _source(tmp_path: Path, local_date: date) -> tuple[TaifexOfficialHistorySource, FixtureTransport]:
    transport = FixtureTransport(local_date)
    return (
        TaifexOfficialHistorySource(
            tmp_path / "taifex.json",
            transport=transport,
            daily_lookback_days=330,
            intraday_trading_days=12,
            workers=2,
        ),
        transport,
    )


def test_official_source_builds_all_closed_timeframes_and_atomic_cache(tmp_path) -> None:
    local_date = date(2026, 8, 20)
    source, transport = _source(tmp_path, local_date)

    result = source.fetch(observed_at=datetime(2026, 8, 20, 2, tzinfo=UTC))

    payload = result.safe_payload()
    assert payload["candle_counts"]["5m"] >= 60
    assert payload["candle_counts"]["15m"] >= 48
    assert payload["candle_counts"]["60m"] >= 36
    assert payload["candle_counts"]["1d"] == 45
    assert payload["candle_counts"]["1w"] >= 39
    assert result.source_trading_dates[-1] < local_date
    assert set(result.selected_contract_months) == {"202608"}
    assert result.official_request_count == 25
    assert len(result.source_hash) == 64
    assert (tmp_path / "taifex.json").is_file()
    assert len(transport.calls) == 25


def test_same_day_restart_uses_hash_verified_cache_without_network(tmp_path) -> None:
    local_date = date(2026, 8, 20)
    source, _ = _source(tmp_path, local_date)
    observed_at = datetime(2026, 8, 20, 2, tzinfo=UTC)
    first = source.fetch(observed_at=observed_at)

    def offline(*_args):
        raise AssertionError("cache hit must not use network")

    cached = TaifexOfficialHistorySource(
        tmp_path / "taifex.json",
        transport=offline,
        daily_lookback_days=330,
        intraday_trading_days=12,
    ).fetch(observed_at=observed_at)

    assert cached.cache_hit is True
    assert cached.official_request_count == 0
    assert cached.source_hash == first.source_hash


def test_after_hours_remains_fail_closed(tmp_path) -> None:
    source, _ = _source(tmp_path, date(2026, 8, 20))
    with pytest.raises(TaifexOfficialHistoryError, match="AFTER_HOURS"):
        source.fetch(
            observed_at=datetime(2026, 8, 20, 2, tzinfo=UTC),
            after_hours=True,
        )


def test_live_verifier_reaches_ready_with_official_closed_history(tmp_path) -> None:
    source, _ = _source(tmp_path, date(2026, 8, 20))
    clients = AuthorizedMarketDataClients(WebSocket(), Rest(), WebSocket(), Rest())
    resolver = VerifiedContractResolver((
        ResolvedFuturesContract(Instrument.TMF, "TMFH6", False),
    ))
    pipeline = FubonFiveTimeframeCandlePipeline(
        FubonIntradayCandlesAdapter(clients, resolver)
    )
    verifier = FubonLiveFiveTimeframeVerifier(pipeline, source)

    payload = verifier.run(
        symbol="TMFH6",
        session=None,
        verified_at=datetime(2026, 8, 20, 2, tzinfo=UTC),
    )

    assert payload["success"] is True
    assert payload["status"] == "READY_VERIFIED_FIVE_TIMEFRAMES"
    assert payload["source_kind"] == "FUBON_LIVE_INTRADAY_PLUS_TAIFEX_OFFICIAL_HISTORY"
    assert payload["taifex_history"]["market_data_only"] is True
    assert payload["live_order_allowed"] is False
    assert verifier.latest_candle_result.series
    assert all(
        values[-1].end <= datetime(2026, 8, 20, 2, tzinfo=UTC)
        for values in tuple(verifier.latest_candle_result.series.values())[:3]
    )
