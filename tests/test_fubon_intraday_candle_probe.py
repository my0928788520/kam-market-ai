import json

from kam_market_ai.authorization.bootstrap import BootstrapResult
from kam_market_ai.market_data.fubon_intraday_candle_probe import FubonIntradayCandleProbe
from kam_market_ai.market_data.fubon_intraday_candle_probe_cli import main
from kam_market_ai.market_data.fubon_neo import AuthorizedMarketDataClients
from kam_market_ai.models import Instrument


class WebSocket:
    def on(self, *_args): pass
    def off(self, *_args): pass
    def connect(self): pass
    def subscribe(self, *_args): pass
    def unsubscribe(self, *_args): pass
    def disconnect(self): pass


class Intraday:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def candles(self, **params: object) -> dict[str, object]:
        self.calls.append(params)
        return {
            "symbol": params["symbol"],
            "timeframe": params["timeframe"],
            "data": [
                {
                    "date": "2026-08-10T01:00:00+08:00",
                    "open": 22000,
                    "high": 22020,
                    "low": 21990,
                    "close": 22010,
                    "volume": 12,
                }
            ],
        }


class Rest:
    def __init__(self, intraday: Intraday) -> None:
        self.intraday = intraday
        self.historical = object()


def clients() -> tuple[AuthorizedMarketDataClients, Intraday]:
    intraday = Intraday()
    value = AuthorizedMarketDataClients(WebSocket(), Rest(intraday), WebSocket(), Rest(Intraday()))
    return value, intraday


def test_probe_invokes_exactly_one_documented_endpoint_and_returns_only_summary() -> None:
    authorized, intraday = clients()
    report = FubonIntradayCandleProbe(authorized).run(
        instrument=Instrument.MTX,
        symbol="MXFH6",
        session="REGULAR",
        timeframe="60",
        interval_minutes=60,
    )
    assert intraday.calls == [{"symbol": "MXFH6", "session": "REGULAR", "timeframe": "60"}]
    payload = report.safe_payload()
    assert payload["success"] is True
    assert payload["candle_count"] == 1
    assert payload["endpoint_invoked"] is True
    assert payload["trading_enabled"] is False
    assert payload["raw_payload_retained"] is False
    assert "data" not in payload


class NeverBootstrap:
    def run(self, *_args, **_kwargs):
        raise AssertionError("bootstrap must not run without --live")


def test_cli_requires_explicit_live_before_bootstrap(capsys) -> None:
    code = main(
        [
            "--instrument", "MTX", "--symbol", "MXFH6", "--session", "REGULAR",
            "--timeframe", "60", "--interval-minutes", "60",
        ],
        bootstrap=NeverBootstrap(),
    )
    assert code == 2
    assert json.loads(capsys.readouterr().out)["failure_stage"] == "LIVE_FLAG_REQUIRED"


class Bootstrap:
    def __init__(self, authorized: AuthorizedMarketDataClients) -> None:
        self.authorized = authorized

    def run(self, *_args, **_kwargs) -> BootstrapResult:
        return BootstrapResult(False, (), self.authorized)


def test_cli_runs_one_sanitized_offline_fixture(monkeypatch, capsys) -> None:
    authorized, intraday = clients()
    monkeypatch.setattr(
        "kam_market_ai.market_data.fubon_intraday_candle_probe_cli.Settings.load",
        lambda _path: object(),
    )
    monkeypatch.setattr(
        "kam_market_ai.market_data.fubon_intraday_candle_probe_cli.AuthorizationSettings.from_local_env",
        lambda _path: object(),
    )
    code = main(
        [
            "--live", "--env", "fixture.env", "--instrument", "TX", "--symbol", "TXFH6",
            "--session", "AFTERHOURS", "--timeframe", "15", "--interval-minutes", "15",
            "--after-hours",
        ],
        bootstrap=Bootstrap(authorized),
    )
    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert payload["symbol"] == "TXFH6"
    assert payload["account_connected"] is False
    assert intraday.calls == [{"symbol": "TXFH6", "session": "AFTERHOURS", "timeframe": "15"}]
