"""Cross-layer acceptance for the complete read-only live decision path."""

import json

from kam_market_ai.dashboard.app import DashboardApp
from kam_market_ai.live_read_only.five_timeframe_snapshot import write_five_timeframe_snapshot
from kam_market_ai.market_data.fubon_five_timeframe_pipeline import FubonFiveTimeframeCandlePipeline
from kam_market_ai.market_data.fubon_live_five_timeframe_verifier import FubonLiveFiveTimeframeVerifier
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
    def __init__(self): self.calls = []
    def candles(self, **params):
        self.calls.append(params)
        return {"symbol": params["symbol"], "timeframe": params["timeframe"], "data": [
            {"date": "2026-08-14T08:45:00+08:00", "open": 22000, "high": 22030, "low": 21990, "close": 22020, "volume": 20},
            {"date": "2026-08-14T09:45:00+08:00", "open": 22020, "high": 22050, "low": 22010, "close": 22040, "volume": 22},
        ]}


class Rest:
    def __init__(self, intraday):
        self.intraday = intraday
        self.historical = object()


def test_provider_to_dashboard_chain_is_read_only_and_three_second_readable(tmp_path):
    intraday = Intraday()
    clients = AuthorizedMarketDataClients(WebSocket(), Rest(intraday), WebSocket(), Rest(Intraday()))
    resolver = VerifiedContractResolver((ResolvedFuturesContract(Instrument.TMF, "TMFH6", False),))
    verifier = FubonLiveFiveTimeframeVerifier(FubonFiveTimeframeCandlePipeline(
        FubonIntradayCandlesAdapter(clients, resolver),
    ))

    verified = verifier.run(symbol="TMFH6", session=None)
    snapshot = write_five_timeframe_snapshot(tmp_path / "live.json", verified)
    app = DashboardApp(five_timeframe_snapshot_path=snapshot)
    api_response = {}
    api_body = b"".join(app(
        {"PATH_INFO": "/api/five-timeframe", "REQUEST_METHOD": "GET"},
        lambda status, headers: api_response.update(status=status, headers=dict(headers)),
    ))
    page_response = {}
    page = b"".join(app(
        {"PATH_INFO": "/five-timeframe", "REQUEST_METHOD": "GET"},
        lambda status, headers: page_response.update(status=status, headers=dict(headers)),
    )).decode("utf-8")

    payload = json.loads(api_body)
    assert [call["timeframe"] for call in intraday.calls] == ["5", "15", "60"]
    assert api_response["status"] == page_response["status"] == "200 OK"
    assert api_response["headers"]["Cache-Control"] == "no-store"
    assert payload["decision_preview"]["direction"] in {"偏多", "偏空", "觀望"}
    assert payload["decision_preview"]["action"] == "HOLD"
    assert payload["market_data_only"] is True
    assert payload["trading_enabled"] is False
    assert payload["live_order_allowed"] is False
    assert "KAM 市場方向" in page
    assert "唯一下一步" in page
    assert "禁止真實下單" in page
    assert "place_order" not in page.lower()
    assert not any(key in payload for key in ("candles", "series", "raw_payload", "orders"))
