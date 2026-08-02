import asyncio
import ast
import json
import unittest
from datetime import datetime, timezone
from pathlib import Path

from kam_market_ai.market_data.fubon_neo import (
    AuthorizedMarketDataClients,
    FubonFuturesDiscovery,
    FubonNeoMarketDataAdapter,
    MarketDataBoundaryError,
    ResolvedFuturesContract,
    VerifiedContractResolver,
)
from kam_market_ai.models import Candle, Instrument


class FakeWebSocket:
    def __init__(self) -> None:
        self.handlers: list[object] = []
        self.connect_calls = 0
        self.disconnect_calls = 0
        self.subscriptions: list[dict[str, object]] = []
        self.unsubscriptions: list[dict[str, object]] = []

    def on(self, event: str, listener: object) -> None:
        assert event == "message"
        self.handlers.append(listener)

    def off(self, event: str, listener: object) -> None:
        assert event == "message"
        self.handlers.remove(listener)

    def connect(self) -> None:
        self.connect_calls += 1

    def subscribe(self, params: dict[str, object]) -> None:
        self.subscriptions.append(dict(params))

    def unsubscribe(self, params: dict[str, object]) -> None:
        self.unsubscriptions.append(dict(params))

    def disconnect(self) -> None:
        self.disconnect_calls += 1

    def emit(self, payload: dict[str, object]) -> None:
        for handler in tuple(self.handlers):
            handler(json.dumps(payload))  # type: ignore[operator]


class FakeIntraday:
    def __init__(self) -> None:
        self.params: dict[str, object] | None = None

    def tickers(self, **params: object) -> dict[str, object]:
        self.params = params
        return {"data": []}


class FakeHistorical:
    def __init__(self) -> None:
        self.params: dict[str, object] | None = None

    def candles(self, **params: object) -> object:
        self.params = params
        return {"fixture": True}


class FakeFutoptRest:
    def __init__(self) -> None:
        self.intraday = FakeIntraday()
        self.historical = FakeHistorical()


class FakeStockRest:
    intraday = object()
    historical = object()


class FixtureRequestMapper:
    def build(self, contract: ResolvedFuturesContract, start: datetime, end: datetime,
              interval_minutes: int) -> dict[str, object]:
        return {"verified_symbol": contract.symbol, "fixture_interval": interval_minutes}


class FixtureDecoder:
    def decode(self, instrument: Instrument, payload: object) -> list[Candle]:
        assert payload == {"fixture": True}
        start = datetime(2026, 7, 14, 1, tzinfo=timezone.utc)
        return [Candle(instrument, start, start, 1, 2, 1, 2, 3)]


def build_adapter() -> tuple[FubonNeoMarketDataAdapter, FakeWebSocket, FakeWebSocket, FakeFutoptRest]:
    futures_ws = FakeWebSocket()
    stock_ws = FakeWebSocket()
    futures_rest = FakeFutoptRest()
    clients = AuthorizedMarketDataClients(futures_ws, futures_rest, stock_ws, FakeStockRest())
    resolver = VerifiedContractResolver([
        ResolvedFuturesContract(Instrument.TX, "VERIFIED_TX_DAY", False),
        ResolvedFuturesContract(Instrument.TX, "VERIFIED_TX_NIGHT", True),
        ResolvedFuturesContract(Instrument.MTX, "VERIFIED_MTX_DAY", False),
        ResolvedFuturesContract(Instrument.MTX, "VERIFIED_MTX_NIGHT", True),
    ])
    return (FubonNeoMarketDataAdapter(clients, resolver, FixtureRequestMapper(), FixtureDecoder()),
            futures_ws, stock_ws, futures_rest)


class FubonNeoAdapterTests(unittest.TestCase):
    def test_futures_tick_conversion_preserves_night_metadata(self) -> None:
        adapter, futures_ws, _, _ = build_adapter()

        async def receive() -> object:
            stream = adapter.stream_ticks((Instrument.MTX,), after_hours=True)
            pending = asyncio.create_task(anext(stream))
            await asyncio.sleep(0)
            futures_ws.emit({"event": "data", "channel": "trades", "data": {
                "symbol": "VERIFIED_MTX_NIGHT", "time": 1720000000000000,
                "trades": [{"price": 21000, "size": 2}],
            }})
            tick = await pending
            await stream.aclose()
            return tick

        tick = asyncio.run(receive())
        self.assertEqual((tick.instrument, tick.price, tick.volume), (Instrument.MTX, 21000.0, 2))
        self.assertEqual((tick.source_symbol, tick.source_channel, tick.after_hours),
                         ("VERIFIED_MTX_NIGHT", "trades", True))
        self.assertEqual(futures_ws.subscriptions, [{"channel": "trades", "symbol": "VERIFIED_MTX_NIGHT", "afterHours": True}])
        self.assertEqual(futures_ws.unsubscriptions, futures_ws.subscriptions)
        self.assertEqual(futures_ws.disconnect_calls, 1)

    def test_taiex_indices_conversion_uses_official_symbol(self) -> None:
        adapter, _, stock_ws, _ = build_adapter()

        async def receive() -> object:
            stream = adapter.stream_ticks((Instrument.TAIEX,))
            pending = asyncio.create_task(anext(stream))
            await asyncio.sleep(0)
            stock_ws.emit({"event": "data", "channel": "indices", "data": {
                "symbol": "IR0001", "index": 22000.5, "time": 1720000000000000,
            }})
            tick = await pending
            await stream.aclose()
            return tick

        tick = asyncio.run(receive())
        self.assertEqual((tick.instrument, tick.price, tick.source_symbol, tick.after_hours),
                         (Instrument.TAIEX, 22000.5, "IR0001", False))
        self.assertEqual(stock_ws.subscriptions, [{"channel": "indices", "symbol": "IR0001"}])
        self.assertEqual(stock_ws.unsubscriptions, stock_ws.subscriptions)
        self.assertEqual(stock_ws.disconnect_calls, 1)

    def test_historical_port_uses_injected_verified_mapping(self) -> None:
        adapter, _, _, rest = build_adapter()
        candles = asyncio.run(adapter.historical_candles(
            Instrument.MTX, datetime(2026, 1, 1), datetime(2026, 1, 2), 60
        ))
        self.assertEqual(rest.historical.params, {"verified_symbol": "VERIFIED_MTX_DAY", "fixture_interval": 60})
        self.assertEqual((len(candles), candles[0].instrument), (1, Instrument.MTX))

    def test_discovery_is_explicit_and_does_not_map_contracts(self) -> None:
        _, _, _, rest = build_adapter()
        response = FubonFuturesDiscovery(rest).list_tickers(type="FUTURE", exchange="TAIFEX")
        self.assertEqual(response, {"data": []})
        self.assertEqual(rest.intraday.params, {"type": "FUTURE", "exchange": "TAIFEX"})

    def test_boundary_rejects_sdk_like_objects_and_adapter_has_no_trade_surface(self) -> None:
        class SdkLike:
            def login(self) -> None: pass
        with self.assertRaises(MarketDataBoundaryError):
            AuthorizedMarketDataClients(SdkLike(), FakeFutoptRest(), FakeWebSocket(), FakeStockRest())
        adapter, _, _, _ = build_adapter()
        for forbidden in ("login", "apikey_login", "accounting", "stock", "futopt", "place_order"):
            self.assertFalse(hasattr(adapter, forbidden))
        module = Path("src/kam_market_ai/market_data/fubon_neo.py").read_text(encoding="utf-8")
        imports = [node for node in ast.walk(ast.parse(module)) if isinstance(node, (ast.Import, ast.ImportFrom))]
        self.assertFalse(any(getattr(node, "module", "") == "fubon_neo.sdk" for node in imports))


if __name__ == "__main__":
    unittest.main()
