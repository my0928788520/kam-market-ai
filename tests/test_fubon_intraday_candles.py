from datetime import UTC, datetime

import pytest

from kam_market_ai.market_data.fubon_neo import (
    AuthorizedMarketDataClients,
    FubonIntradayCandlesAdapter,
    IntradayCandleContractError,
    OfficialIntradayCandleSpec,
    ResolvedFuturesContract,
    VerifiedContractResolver,
)
from kam_market_ai.models import Instrument


class FakeWebSocket:
    def on(self, event: str, listener: object) -> None: pass
    def off(self, event: str, listener: object) -> None: pass
    def connect(self) -> None: pass
    def subscribe(self, params: object) -> None: pass
    def unsubscribe(self, params: object) -> None: pass
    def disconnect(self) -> None: pass


class FakeIntraday:
    def __init__(self, payload: object) -> None:
        self.payload = payload
        self.calls: list[dict[str, object]] = []

    def candles(self, **params: object) -> object:
        self.calls.append(dict(params))
        return self.payload


class FakeRest:
    def __init__(self, intraday: FakeIntraday) -> None:
        self.intraday = intraday
        self.historical = object()


class FakeStockRest:
    intraday = object()
    historical = object()


def adapter(payload: object) -> tuple[FubonIntradayCandlesAdapter, FakeIntraday]:
    intraday = FakeIntraday(payload)
    clients = AuthorizedMarketDataClients(
        FakeWebSocket(), FakeRest(intraday), FakeWebSocket(), FakeStockRest()
    )
    resolver = VerifiedContractResolver(
        [ResolvedFuturesContract(Instrument.MTX, "VERIFIED_MTX", False)]
    )
    return FubonIntradayCandlesAdapter(clients, resolver), intraday


def payload() -> dict[str, object]:
    return {
        "date": "2026-08-10",
        "type": "FUTURE",
        "exchange": "TAIFEX",
        "market": "FUTURES",
        "symbol": "VERIFIED_MTX",
        "timeframe": "VERIFIED_15",
        "data": [
            {
                "date": "2026-08-10T09:00:00+08:00",
                "open": 21000,
                "high": 21020,
                "low": 20990,
                "close": 21010,
                "volume": 12,
                "average": 21005,
            },
            {
                "date": "2026-08-10T09:15:00+08:00",
                "open": 21010,
                "high": 21030,
                "low": 21000,
                "close": 21025,
                "volume": 8,
                "average": 21018,
            },
        ],
    }


def test_official_intraday_port_passes_only_documented_parameters_and_decodes_offline() -> None:
    value, intraday = adapter(payload())
    candles = value.fetch(
        Instrument.MTX,
        OfficialIntradayCandleSpec("VERIFIED_REGULAR", "VERIFIED_15", 15),
    )

    assert intraday.calls == [
        {
            "symbol": "VERIFIED_MTX",
            "session": "VERIFIED_REGULAR",
            "timeframe": "VERIFIED_15",
        }
    ]
    assert [(item.start, item.end) for item in candles] == [
        (datetime(2026, 8, 10, 1, 0, tzinfo=UTC), datetime(2026, 8, 10, 1, 15, tzinfo=UTC)),
        (datetime(2026, 8, 10, 1, 15, tzinfo=UTC), datetime(2026, 8, 10, 1, 30, tzinfo=UTC)),
    ]
    assert (candles[0].open, candles[0].high, candles[0].low, candles[0].close, candles[0].volume) == (
        21000.0,
        21020.0,
        20990.0,
        21010.0,
        12,
    )


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda value: value.update(symbol="WRONG"), "identity mismatch"),
        (lambda value: value["data"][0].pop("volume"), "missing documented fields"),
        (lambda value: value["data"][0].update(low=22000), "OHLC range"),
        (lambda value: value["data"][0].update(open=float("nan")), "open must be finite"),
        (lambda value: value["data"][0].update(volume=1.5), "volume must be a non-negative integer"),
        (lambda value: value["data"].reverse(), "strictly chronological"),
    ],
)
def test_intraday_decoder_fails_closed_on_untrusted_provider_payload(mutate, message: str) -> None:
    raw = payload()
    mutate(raw)
    value, _ = adapter(raw)

    with pytest.raises(IntradayCandleContractError, match=message):
        value.fetch(
            Instrument.MTX,
            OfficialIntradayCandleSpec("VERIFIED_REGULAR", "VERIFIED_15", 15),
        )


def test_intraday_request_requires_explicit_verified_tokens_before_any_call() -> None:
    value, intraday = adapter(payload())

    with pytest.raises(IntradayCandleContractError, match="session token"):
        value.fetch(Instrument.MTX, OfficialIntradayCandleSpec("", "VERIFIED_15", 15))

    assert intraday.calls == []
