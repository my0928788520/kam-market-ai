import json
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest

from kam_market_ai.live_read_only.market_snapshot import (
    MarketDataSource,
    MarketSnapshotStatus,
)
from kam_market_ai.live_read_only.providers.fubon_futures_runtime import (
    FubonFuturesLiveClient,
    FubonFuturesRuntimeConfig,
    FubonFuturesRuntimeError,
)
from kam_market_ai.live_read_only.runtime_market_source import (
    RuntimeMarketSourceConfig,
    RuntimeMarketSourceMode,
    RuntimeMarketSourceSelector,
    RuntimeMarketSourceStatus,
)
from kam_market_ai.market_data.fubon_neo import AuthorizedMarketDataClients
from kam_market_ai.market_data.futures_live_probe import (
    FubonLiveFuturesContract,
    FuturesProductCode,
)
from kam_market_ai.paper_trading.operator_presenter import PaperTradingOperatorView
from kam_market_ai.paper_trading.operator_wsgi import build_operator_wsgi

NOW = datetime(2026, 8, 10, 1, 0, tzinfo=UTC)
NOW_MICROSECONDS = int(NOW.timestamp() * 1_000_000)


class FakeWebSocket:
    def __init__(self, *, malformed: bool = False) -> None:
        self.listeners: dict[str, list[object]] = {}
        self.unsubscribe_calls: list[dict[str, object]] = []
        self.disconnect_calls = 0
        self.malformed = malformed

    def on(self, event: str, listener: object) -> None:
        self.listeners.setdefault(event, []).append(listener)

    def off(self, event: str, listener: object) -> None:
        self.listeners[event].remove(listener)

    def emit(self, event: str, *args: object) -> None:
        for listener in tuple(self.listeners.get(event, ())):
            listener(*args)  # type: ignore[operator]

    def message(self, payload: dict[str, object]) -> None:
        self.emit("message", json.dumps(payload))

    def connect(self) -> None:
        self.emit("connect")
        self.emit("authenticated", {"message": "ok"})

    def subscribe(self, params: dict[str, object]) -> None:
        symbol = str(params["symbol"])
        self.message(
            {
                "event": "subscribed",
                "data": {"id": f"id-{symbol}", "channel": "trades", "symbol": symbol},
            }
        )
        data: dict[str, object] = {
            "symbol": symbol,
            "trades": [
                {"price": {"TXF": 24101, "MXF": 24102, "TMF": 24103}[symbol[:3]], "size": 2}
            ],
            "time": NOW_MICROSECONDS,
        }
        if self.malformed:
            data.pop("time")
        self.message({"event": "data", "channel": "trades", "data": data})

    def unsubscribe(self, params: dict[str, object]) -> None:
        self.unsubscribe_calls.append(dict(params))
        ids = params.get("ids", [params.get("id")])
        self.message(
            {
                "event": "unsubscribed",
                "data": [
                    {"id": value, "channel": "trades"} for value in ids if isinstance(value, str)
                ],
            }
        )

    def disconnect(self) -> None:
        self.disconnect_calls += 1
        self.emit("disconnect", 1000, "normal")


class FakeRest:
    intraday = object()
    historical = object()


def contracts(*, after_hours: bool = False) -> tuple[FubonLiveFuturesContract, ...]:
    return tuple(
        FubonLiveFuturesContract(
            code,
            {
                FuturesProductCode.TX: "TXFH6",
                FuturesProductCode.MTX: "MXFH6",
                FuturesProductCode.TMF: "TMFH6",
            }[code],
            {
                FuturesProductCode.TX: "TXF202608",
                FuturesProductCode.MTX: "MXF202608",
                FuturesProductCode.TMF: "TMF202608",
            }[code],
            "202608",
            date(2026, 8, 19),
            {FuturesProductCode.TX: 100, FuturesProductCode.MTX: 200, FuturesProductCode.TMF: 300}[
                code
            ],
            after_hours,
        )
        for code in FuturesProductCode
    )


def client(websocket: FakeWebSocket) -> FubonFuturesLiveClient:
    clients = AuthorizedMarketDataClients(websocket, FakeRest(), FakeWebSocket(), FakeRest())
    return FubonFuturesLiveClient(
        clients,
        contracts(),
        FubonFuturesRuntimeConfig(0.1, 0.1, 0.1, 0.1),
        clock=lambda: NOW,
    )


def test_live_client_maps_verified_quotes_into_fail_closed_market_snapshots() -> None:
    websocket = FakeWebSocket()
    live = client(websocket)
    live.start()
    selection = RuntimeMarketSourceSelector().select(
        RuntimeMarketSourceConfig(RuntimeMarketSourceMode.FUBON_LIVE),
        fubon_live_client=live,
    )

    assert selection.is_live_data and not selection.trading_enabled
    assert selection.provider.list_available_products() == ("MTX", "TMF", "TX")
    snapshots = tuple(selection.provider.read_snapshot(code) for code in ("TX", "MTX", "TMF"))
    assert [item.last_price for item in snapshots] == [
        Decimal(24101),
        Decimal(24102),
        Decimal(24103),
    ]
    assert [item.volume for item in snapshots] == [Decimal(102), Decimal(202), Decimal(302)]
    assert all(item.status is MarketSnapshotStatus.READY for item in snapshots)
    assert all(item.data_source is MarketDataSource.FUTURE_LIVE for item in snapshots)
    assert all(not item.account_connected and not item.broker_connected for item in snapshots)
    assert all(not item.trading_enabled and not item.live_order_allowed for item in snapshots)

    selection.provider.close()  # type: ignore[attr-defined]
    assert websocket.unsubscribe_calls == [{"ids": ["id-MXFH6", "id-TMFH6", "id-TXFH6"]}]
    assert websocket.disconnect_calls == 1
    assert all(not listeners for listeners in websocket.listeners.values())


def test_unexpected_disconnect_degrades_runtime_and_snapshot_without_fallback() -> None:
    websocket = FakeWebSocket()
    live = client(websocket)
    live.start()
    provider = (
        RuntimeMarketSourceSelector()
        .select(
            RuntimeMarketSourceConfig(RuntimeMarketSourceMode.FUBON_LIVE),
            fubon_live_client=live,
        )
        .provider
    )

    websocket.emit("disconnect", 1006, "fixture disconnect")

    assert provider.runtime_status() is RuntimeMarketSourceStatus.DEGRADED
    assert provider.list_available_products() == ()
    assert provider.read_snapshot("TX").status is MarketSnapshotStatus.CLIENT_UNAVAILABLE
    assert provider.read_snapshot("TX").last_price is None
    provider.close()  # type: ignore[attr-defined]


def test_malformed_provider_data_fails_with_stable_stage_and_no_raw_values() -> None:
    live = client(FakeWebSocket(malformed=True))
    with pytest.raises(FubonFuturesRuntimeError) as raised:
        live.start()
    assert str(raised.value) in {"SUBSCRIBE_ERROR", "PROVIDER_PAYLOAD_ERROR"}
    assert "24101" not in str(raised.value)


def test_live_dashboard_shows_real_quote_but_never_offline_decision_or_proposal() -> None:
    websocket = FakeWebSocket()
    live = client(websocket)
    live.start()
    provider = (
        RuntimeMarketSourceSelector()
        .select(
            RuntimeMarketSourceConfig(RuntimeMarketSourceMode.FUBON_LIVE),
            fubon_live_client=live,
        )
        .provider
    )
    view = PaperTradingOperatorView(
        "KAM",
        "fixture",
        {"action": "BUY_FIXTURE"},
        {"state": "FILLED_FIXTURE"},
        {"cash": "—"},
        (),
        False,
        demo={
            "direction": "偏多假資料",
            "bull_score": "90",
            "position": "多單假資料",
            "next_step": "買進假資料",
        },
    )
    app = build_operator_wsgi(lambda: view, market_data_source=provider)
    html = b"".join(
        app(
            {"REQUEST_METHOD": "GET", "PATH_INFO": "/", "QUERY_STRING": "instrument=TX"},
            lambda *_: None,
        )
    ).decode()

    for text in (
        "富邦真實期貨行情",
        "WebSocket 連線就緒",
        "TXF202608",
        "24,101",
        "尚未判定",
        "等待四週期資料",
        "等待 K 線",
        "尚未接入真實行情決策",
        "唯讀模式",
        "禁止真實下單",
    ):
        assert text in html
    for text in ("偏多假資料", "BUY_FIXTURE", "FILLED_FIXTURE", "多單假資料", "買進假資料"):
        assert text not in html
    assert "title='FUTURE_LIVE'" in html
    assert "http-equiv='refresh' content='3'" in html
    provider.close()  # type: ignore[attr-defined]


def test_stale_live_record_becomes_stale_without_reusing_offline_data() -> None:
    websocket = FakeWebSocket()
    live = client(websocket)
    live.start()
    live._clock = lambda: NOW + timedelta(seconds=61)  # type: ignore[attr-defined]
    provider = (
        RuntimeMarketSourceSelector()
        .select(
            RuntimeMarketSourceConfig(RuntimeMarketSourceMode.FUBON_LIVE),
            fubon_live_client=live,
        )
        .provider
    )

    snapshot = provider.read_snapshot("TMF")
    assert snapshot.status is MarketSnapshotStatus.STALE
    assert snapshot.data_source is MarketDataSource.FUTURE_LIVE
    provider.close()  # type: ignore[attr-defined]


def test_runtime_surface_has_no_account_order_position_balance_or_execution_methods() -> None:
    forbidden = {"account", "order", "position", "balance", "execution", "place_order"}
    assert not forbidden.intersection(FubonFuturesLiveClient.__dict__)
