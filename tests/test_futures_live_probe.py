import json
from datetime import UTC, date, datetime

import pytest

from kam_market_ai.market_data.fubon_neo import AuthorizedMarketDataClients
from kam_market_ai.market_data.futures_live_probe import (
    FubonFuturesContractDiscovery,
    FubonFuturesLiveProbe,
    FuturesContractDiscoveryError,
    FuturesLiveProbeFailure,
)


NOW = datetime(2026, 8, 9, 1, 0, tzinfo=UTC)
NOW_MICROSECONDS = int(NOW.timestamp() * 1_000_000)


class FakeIntraday:
    def __init__(self, *, ambiguous: bool = False) -> None:
        self.ambiguous = ambiguous
        self.ticker_calls: list[dict[str, object]] = []
        self.quote_calls: list[dict[str, object]] = []

    def tickers(self, **params: object) -> dict[str, object]:
        self.ticker_calls.append(dict(params))
        return {
            "data": [
                {"symbol": "TXHG6", "name": "not-a-monthly-contract", "endDate": "2026-07-15"},
                {"symbol": "TXFH6", "name": "臺股期貨086", "endDate": "2026-08-19"},
                {"symbol": "TXFI6", "name": "臺股期貨096", "endDate": "2026-09-16"},
                {"symbol": "MXFH6", "name": "小型臺指期貨086", "endDate": "2026-08-19"},
                {"symbol": "TMFH6", "name": "微型臺指期貨086", "endDate": "2026-08-19"},
            ]
        }

    def quote(self, **params: object) -> dict[str, object]:
        self.quote_calls.append(dict(params))
        volume = {"TXFH6": 100, "TXFI6": 100 if self.ambiguous else 200, "MXFH6": 300, "TMFH6": 400}
        return {"total": {"tradeVolume": volume[str(params["symbol"])]}}


class FakeRest:
    def __init__(self, intraday: FakeIntraday) -> None:
        self.intraday = intraday
        self.historical = object()


class FakeWebSocket:
    def __init__(self, *, malformed_product: str | None = None) -> None:
        self.listeners: dict[str, list[object]] = {}
        self.connect_calls = 0
        self.subscribe_calls: list[dict[str, object]] = []
        self.unsubscribe_calls: list[dict[str, object]] = []
        self.disconnect_calls = 0
        self.malformed_product = malformed_product

    def on(self, event: str, listener: object) -> None:
        self.listeners.setdefault(event, []).append(listener)

    def off(self, event: str, listener: object) -> None:
        self.listeners[event].remove(listener)

    def _emit(self, event: str, *args: object) -> None:
        for listener in tuple(self.listeners.get(event, ())):
            listener(*args)  # type: ignore[operator]

    def _message(self, payload: dict[str, object]) -> None:
        self._emit("message", json.dumps(payload))

    def connect(self) -> None:
        self.connect_calls += 1
        self._emit("connect")
        self._emit("authenticated", {"message": "ok"})

    def subscribe(self, params: dict[str, object]) -> None:
        self.subscribe_calls.append(dict(params))
        symbol = str(params["symbol"])
        channel_id = f"cycle-{self.connect_calls}-{symbol}"
        self._message(
            {
                "event": "subscribed",
                "data": {"id": channel_id, "channel": "trades", "symbol": symbol},
            }
        )
        product = {"TXF": "TX", "MXF": "MTX", "TMF": "TMF"}[symbol[:3]]
        data: dict[str, object] = {
            "symbol": symbol,
            "trades": [{"price": 24100, "size": 1}],
            "time": NOW_MICROSECONDS,
        }
        if product == self.malformed_product:
            data.pop("time")
        self._message({"event": "data", "channel": "trades", "data": data})

    def unsubscribe(self, params: dict[str, object]) -> None:
        self.unsubscribe_calls.append(dict(params))
        ids = params.get("ids", [params.get("id")])
        data = [{"id": value, "channel": "trades"} for value in ids if isinstance(value, str)]
        self._message({"event": "unsubscribed", "data": data})

    def disconnect(self) -> None:
        self.disconnect_calls += 1
        self._emit("disconnect", 1000, "normal")


class FakeStockRest:
    intraday = object()
    historical = object()


def clients(
    websocket: FakeWebSocket | None = None,
    intraday: FakeIntraday | None = None,
) -> AuthorizedMarketDataClients:
    websocket = websocket or FakeWebSocket()
    rest = FakeRest(intraday or FakeIntraday())
    return AuthorizedMarketDataClients(websocket, rest, FakeWebSocket(), FakeStockRest())


def contracts(value: AuthorizedMarketDataClients):
    return FubonFuturesContractDiscovery(value).resolve(today=date(2026, 8, 9))


def test_contract_discovery_resolves_all_three_products_and_canonical_months() -> None:
    intraday = FakeIntraday()
    result = contracts(clients(intraday=intraday))

    assert [(item.product_code.value, item.provider_symbol) for item in result] == [
        ("TX", "TXFI6"),
        ("MTX", "MXFH6"),
        ("TMF", "TMFH6"),
    ]
    assert [item.contract_code for item in result] == ["TXF202609", "MXF202608", "TMF202608"]
    assert intraday.ticker_calls == [
        {"type": "FUTURE", "exchange": "TAIFEX", "session": "REGULAR", "contractType": "I"}
    ]


def test_after_hours_discovery_uses_documented_session_parameters() -> None:
    intraday = FakeIntraday()
    value = clients(intraday=intraday)
    FubonFuturesContractDiscovery(value).resolve(after_hours=True, today=date(2026, 8, 9))

    assert intraday.ticker_calls[0]["session"] == "AFTERHOURS"
    assert all(call["session"] == "afterhours" for call in intraday.quote_calls)


def test_discovery_fails_closed_on_equal_highest_volume() -> None:
    with pytest.raises(FuturesContractDiscoveryError, match="AMBIGUOUS_TX_CONTRACT"):
        contracts(clients(intraday=FakeIntraday(ambiguous=True)))


def test_live_probe_verifies_three_products_cleanup_and_controlled_reconnect() -> None:
    websocket = FakeWebSocket()
    value = clients(websocket=websocket)
    report = FubonFuturesLiveProbe(
        value,
        clock=lambda: NOW,
        connect_timeout_seconds=0.1,
        subscribe_timeout_seconds=0.1,
        cleanup_timeout_seconds=0.1,
    ).run(contracts(value), duration_seconds=0.1, verify_reconnect=True)

    assert report.success
    assert [cycle.phase for cycle in report.cycles] == ["initial", "controlled-reconnect"]
    assert websocket.connect_calls == 2 and websocket.disconnect_calls == 2
    assert len(websocket.subscribe_calls) == 6 and len(websocket.unsubscribe_calls) == 2
    assert all(set(call) == {"ids"} for call in websocket.unsubscribe_calls)
    assert all(set(dict(cycle.data_event_count).values()) == {1} for cycle in report.cycles)


def test_probe_rejects_malformed_timestamp_and_never_exposes_raw_or_trading_state() -> None:
    websocket = FakeWebSocket(malformed_product="MTX")
    value = clients(websocket=websocket)
    report = FubonFuturesLiveProbe(
        value,
        clock=lambda: NOW,
        connect_timeout_seconds=0.05,
        subscribe_timeout_seconds=0.05,
        cleanup_timeout_seconds=0.05,
    ).run(contracts(value), duration_seconds=0.01)

    assert report.failure_stage is FuturesLiveProbeFailure.PROVIDER_PAYLOAD_ERROR
    safe = json.dumps(report.safe_payload())
    assert "price" not in safe and "password" not in safe and "certificate" not in safe
    assert report.market_data_only
    assert not report.account_connected
    assert not report.broker_connected
    assert not report.trading_enabled
    assert not report.live_order_allowed


def test_probe_surface_has_no_order_account_position_or_balance_methods() -> None:
    forbidden = {"order", "account", "position", "balance", "trade"}
    assert not forbidden.intersection(FubonFuturesLiveProbe.__dict__)
