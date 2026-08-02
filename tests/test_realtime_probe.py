import json
import tempfile
import unittest
from datetime import date

from kam_market_ai.market_data.fubon_neo import AuthorizedMarketDataClients
from kam_market_ai.market_data.realtime_probe import ActiveContractProbe, ActiveContracts, BoundedReactionObserver


class ProbeWebSocket:
    def __init__(self, messages: dict[str, dict[str, object]]) -> None:
        self.messages = messages
        self.handlers: list[object] = []
        self.unsubscribed: list[dict[str, object]] = []
        self.disconnect_calls = 0

    def on(self, event: str, listener: object) -> None:
        self.handlers.append(listener)

    def off(self, event: str, listener: object) -> None:
        self.handlers.remove(listener)

    def connect(self) -> None:
        return None

    def subscribe(self, params: dict[str, object]) -> None:
        message = self.messages.get(str(params["symbol"]))
        if message:
            for handler in tuple(self.handlers):
                handler(json.dumps(message))  # type: ignore[operator]

    def unsubscribe(self, params: dict[str, object]) -> None:
        self.unsubscribed.append(dict(params))

    def disconnect(self) -> None:
        self.disconnect_calls += 1


class ProbeIntraday:
    def tickers(self, **_: object) -> dict[str, object]:
        return {"data": [
            {"symbol": "TXFG6", "name": "臺股期貨076", "endDate": "2026-07-15"},
            {"symbol": "TXFH6", "name": "臺股期貨086", "endDate": "2026-08-19"},
            {"symbol": "TMFG6", "name": "微型臺指期貨076", "endDate": "2026-07-15"},
            {"symbol": "TMFH6", "name": "微型臺指期貨086", "endDate": "2026-08-19"},
        ]}

    def quote(self, *, symbol: str, **_: object) -> dict[str, object]:
        volumes = {"TXFG6": 50, "TXFH6": 90, "TMFG6": 100, "TMFH6": 20}
        return {"total": {"tradeVolume": volumes[symbol]}}


class ProbeRest:
    def __init__(self) -> None:
        self.intraday = ProbeIntraday()
        self.historical = object()


class StockRest:
    intraday = object()
    historical = object()


class RealtimeProbeTests(unittest.TestCase):
    def test_activity_selects_volume_not_nearest_contract(self) -> None:
        clients = AuthorizedMarketDataClients(ProbeWebSocket({}), ProbeRest(), ProbeWebSocket({}), StockRest())
        active = ActiveContractProbe(clients).resolve(today=date(2026, 7, 14))
        self.assertEqual((active.tx_symbol, active.tmf_symbol), ("TXFH6", "TMFG6"))

    def test_bounded_observer_maps_and_cleans_up_without_raw_payload_storage(self) -> None:
        futures = ProbeWebSocket({
            "TXFH6": {"event": "data", "channel": "trades", "data": {"symbol": "TXFH6", "time": 1720000000100000, "trades": [{"price": 200, "size": 2}]}},
            "TMFG6": {"event": "data", "channel": "trades", "data": {"symbol": "TMFG6", "time": 1720000000200000, "trades": [{"price": 300, "size": 3}]}},
        })
        stock = ProbeWebSocket({
            "IR0001": {"event": "data", "channel": "indices", "data": {"symbol": "IR0001", "index": 100, "time": 1720000000000000}},
        })
        clients = AuthorizedMarketDataClients(futures, ProbeRest(), stock, StockRest())
        with tempfile.TemporaryDirectory() as directory:
            report = BoundedReactionObserver(clients, f"{directory}/probe.db").observe(
                ActiveContracts("TXFH6", "TMFG6"), duration_seconds=0.01
            )
        self.assertEqual(report.event_count_by_instrument, {"TX": 1, "MTX": 1, "TAIEX": 1})
        self.assertEqual((report.event_cluster_count, report.reaction_analysis_count, report.reaction_storage_count), (1, 1, 1))
        self.assertTrue(report.unsubscribe_success)
        self.assertTrue(report.disconnect_success)
        self.assertEqual((len(futures.unsubscribed), len(stock.unsubscribed)), (2, 1))
        self.assertEqual((futures.disconnect_calls, stock.disconnect_calls), (1, 1))


if __name__ == "__main__":
    unittest.main()
