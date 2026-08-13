import json
from datetime import date

from kam_market_ai.authorization.bootstrap import BootstrapResult
from kam_market_ai.market_data.fubon_neo import AuthorizedMarketDataClients
from kam_market_ai.market_data.fubon_tmf_contract_probe import FubonTmfContractProbe
from kam_market_ai.market_data.fubon_tmf_contract_probe_cli import main


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

    def tickers(self, **params: object) -> dict[str, object]:
        self.calls.append(dict(params))
        return {"data": [
            {"symbol": "FITMN08", "name": "微型臺指期貨086", "endDate": "2026-08-19"},
            {"symbol": "TMFI6", "name": "微型臺指期貨096", "endDate": "2026-09-16"},
            {"symbol": "TMFH6", "name": "微型臺指期貨086", "endDate": "2026-08-19"},
            {"symbol": "MXFH6", "name": "小型臺指086", "endDate": "2026-08-19"},
            {"symbol": "TMFG6", "name": "微型臺指期貨076", "endDate": "2026-07-15"},
        ]}

    def quote(self, **params: object) -> dict[str, object]:
        self.calls.append(dict(params))
        return {"total": {"tradeVolume": {"TMFH6": 500, "TMFI6": 100}[str(params["symbol"])]}}


class Rest:
    def __init__(self, intraday: Intraday) -> None:
        self.intraday = intraday
        self.historical = object()


def clients() -> tuple[AuthorizedMarketDataClients, Intraday]:
    intraday = Intraday()
    value = AuthorizedMarketDataClients(WebSocket(), Rest(intraday), WebSocket(), Rest(Intraday()))
    return value, intraday


def test_probe_calls_tickers_once_and_returns_only_verified_tmf_candidates() -> None:
    authorized, intraday = clients()
    report = FubonTmfContractProbe(authorized).run(after_hours=True, today=date(2026, 8, 10))
    assert intraday.calls == [{
        "type": "FUTURE", "exchange": "TAIFEX", "session": "AFTERHOURS", "contractType": "I",
    }]
    assert [item.symbol for item in report.candidates] == ["TMFH6", "TMFI6"]
    payload = report.safe_payload()
    assert payload["endpoint_call_count"] == 1
    assert payload["quote_endpoint_invoked"] is False
    assert payload["raw_payload_retained"] is False
    assert payload["trading_enabled"] is False


def test_probe_resolves_unique_active_contract_by_documented_quote_volume() -> None:
    authorized, intraday = clients()

    active = FubonTmfContractProbe(authorized).resolve_active(today=date(2026, 8, 10))

    assert active.symbol == "TMFH6"
    assert intraday.calls[1:] == [{"symbol": "TMFH6"}, {"symbol": "TMFI6"}]


class NeverBootstrap:
    def run(self, *_args, **_kwargs):
        raise AssertionError("bootstrap must not run without --live")


def test_cli_requires_explicit_live_before_bootstrap(capsys) -> None:
    assert main([], bootstrap=NeverBootstrap()) == 2
    assert json.loads(capsys.readouterr().out)["failure_stage"] == "LIVE_FLAG_REQUIRED"


class Bootstrap:
    def __init__(self, authorized: AuthorizedMarketDataClients) -> None:
        self.authorized = authorized

    def run(self, *_args, **_kwargs) -> BootstrapResult:
        return BootstrapResult(False, (), self.authorized)


def test_cli_returns_sanitized_candidates_from_offline_fixture(monkeypatch, capsys) -> None:
    authorized, _ = clients()
    monkeypatch.setattr(
        "kam_market_ai.market_data.fubon_tmf_contract_probe_cli.Settings.load",
        lambda _path: object(),
    )
    monkeypatch.setattr(
        "kam_market_ai.market_data.fubon_tmf_contract_probe_cli.AuthorizationSettings.from_local_env",
        lambda _path: object(),
    )
    monkeypatch.setattr(
        "kam_market_ai.market_data.fubon_tmf_contract_probe.datetime",
        type("Clock", (), {"now": staticmethod(lambda _zone: type("Now", (), {"date": lambda self: date(2026, 8, 10)})())}),
    )
    code = main(["--live", "--env", "fixture.env", "--after-hours"], bootstrap=Bootstrap(authorized))
    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert [item["symbol"] for item in payload["candidates"]] == ["TMFH6", "TMFI6"]
    assert "FITMN08" not in json.dumps(payload)
