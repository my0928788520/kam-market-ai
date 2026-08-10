from pathlib import Path

from kam_market_ai.market_data.fubon_five_timeframe_pipeline import (
    REQUIRED_FIVE_TIMEFRAMES,
    FubonFiveTimeframeCandlePipeline,
)
from kam_market_ai.market_data.fubon_neo import (
    AuthorizedMarketDataClients,
    FubonIntradayCandlesAdapter,
    ResolvedFuturesContract,
    VerifiedContractResolver,
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
    def __init__(self, *, empty_at: str | None = None) -> None:
        self.calls: list[dict[str, object]] = []
        self.empty_at = empty_at

    def candles(self, **params: object) -> dict[str, object]:
        self.calls.append(params)
        rows = [] if params["timeframe"] == self.empty_at else [{
            "date": "2026-08-10T15:00:00+08:00", "open": 22000, "high": 22020,
            "low": 21990, "close": 22010, "volume": 12,
        }]
        return {"symbol": params["symbol"], "timeframe": params["timeframe"], "data": rows}


class Rest:
    def __init__(self, intraday: Intraday) -> None:
        self.intraday = intraday
        self.historical = object()


def pipeline(intraday: Intraday) -> FubonFiveTimeframeCandlePipeline:
    clients = AuthorizedMarketDataClients(WebSocket(), Rest(intraday), WebSocket(), Rest(Intraday()))
    resolver = VerifiedContractResolver((ResolvedFuturesContract(Instrument.TMF, "TMFH6", True),))
    return FubonFiveTimeframeCandlePipeline(FubonIntradayCandlesAdapter(clients, resolver))


def test_bridge_fetches_only_verified_minute_frames_and_blocks_incomplete_coverage() -> None:
    intraday = Intraday()
    result = pipeline(intraday).run(Instrument.TMF, session="AFTERHOURS", after_hours=True)

    assert intraday.calls == [
        {"symbol": "TMFH6", "session": "AFTERHOURS", "timeframe": "5"},
        {"symbol": "TMFH6", "session": "AFTERHOURS", "timeframe": "15"},
        {"symbol": "TMFH6", "session": "AFTERHOURS", "timeframe": "60"},
    ]
    assert tuple(result.series) == REQUIRED_FIVE_TIMEFRAMES[:3]
    assert result.missing_timeframes == REQUIRED_FIVE_TIMEFRAMES[3:]
    payload = result.safe_payload()
    assert payload["status"] == "BLOCKED_INCOMPLETE_COVERAGE"
    assert payload["loaded_timeframes"] == ["5m", "15m", "60m"]
    assert payload["missing_timeframes"] == ["1d", "1w"]
    assert payload["endpoint_call_count"] == 3
    assert payload["trading_enabled"] is False
    assert payload["raw_payload_retained"] is False
    assert "series" not in payload and "candles" not in payload


def test_bridge_fails_closed_on_empty_intraday_slice_without_claiming_five_frame_result() -> None:
    intraday = Intraday(empty_at="15")
    try:
        pipeline(intraday).run(Instrument.TMF, session="AFTERHOURS", after_hours=True)
    except ValueError as error:
        assert str(error) == "FIVE_TIMEFRAME_EMPTY_15M"
    else:
        raise AssertionError("empty verified slice must fail closed")
    assert [call["timeframe"] for call in intraday.calls] == ["5", "15"]


def test_bridge_module_contains_no_account_or_order_capability() -> None:
    import kam_market_ai.market_data.fubon_five_timeframe_pipeline as module

    source = Path(module.__file__).read_text(encoding="utf-8").lower()
    assert "account" not in source
    assert "place_order" not in source
    assert "subscribe(" not in source
