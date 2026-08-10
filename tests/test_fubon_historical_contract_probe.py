import json

from kam_market_ai.authorization.bootstrap import BootstrapResult
from kam_market_ai.market_data.fubon_historical_contract_probe import (
    HistoricalContractProbeError,
    probe_fubon_historical_contract,
)
from kam_market_ai.market_data.fubon_historical_contract_probe_cli import main
from kam_market_ai.market_data.fubon_neo import AuthorizedMarketDataClients


class WebSocket:
    def on(self, event, listener): pass
    def off(self, event, listener): pass
    def connect(self): pass
    def subscribe(self, params): pass
    def unsubscribe(self, params): pass
    def disconnect(self): pass


class Historical:
    def __init__(self) -> None:
        self.calls = 0

    def candles(self, symbol: str, *, timeframe: str = "60") -> object:
        self.calls += 1
        raise AssertionError("probe must not invoke endpoint")


class Rest:
    def __init__(self, historical: object) -> None:
        self.intraday = object()
        self.historical = historical


class StockRest:
    intraday = object()
    historical = object()


def clients(historical: object | None = None) -> tuple[AuthorizedMarketDataClients, Historical]:
    history = historical if historical is not None else Historical()
    assert isinstance(history, Historical)
    return AuthorizedMarketDataClients(WebSocket(), Rest(history), WebSocket(), StockRest()), history


def test_probe_records_signature_without_invoking_endpoint() -> None:
    authorized, history = clients()
    result = probe_fubon_historical_contract(authorized)
    assert history.calls == 0
    assert result.endpoint_invoked is False
    assert result.trading_enabled is False
    assert [item["name"] for item in result.candles_parameters] == ["symbol", "timeframe"]
    assert result.candles_parameters[0]["required"] == "true"
    assert len(result.fingerprint_sha256) == 64


def test_probe_is_deterministic_and_contains_no_runtime_objects() -> None:
    first, _ = clients()
    second, _ = clients()
    left = probe_fubon_historical_contract(first).safe_payload()
    right = probe_fubon_historical_contract(second).safe_payload()
    assert left == right
    json.dumps(left)
    assert "password" not in json.dumps(left).lower()
    assert "account" not in json.dumps(left).lower()


def test_probe_fails_closed_when_candles_is_not_callable() -> None:
    authorized = AuthorizedMarketDataClients(WebSocket(), Rest(type("History", (), {"candles": 1})()), WebSocket(), StockRest())
    try:
        probe_fubon_historical_contract(authorized)
    except HistoricalContractProbeError as error:
        assert str(error) == "CANDLES_NOT_CALLABLE"
    else:
        raise AssertionError("expected fail-closed error")


class Bootstrap:
    def __init__(self, result: BootstrapResult) -> None:
        self.result = result

    def run(self, settings, *, dry_run=True):
        assert dry_run is False
        return self.result


def test_cli_requires_explicit_live_flag(capsys) -> None:
    assert main([], bootstrap=Bootstrap(BootstrapResult(True, ()))) == 2
    assert json.loads(capsys.readouterr().out)["failure_stage"] == "LIVE_FLAG_REQUIRED"


def test_cli_emits_only_safe_contract_evidence(monkeypatch, capsys) -> None:
    authorized, history = clients()
    monkeypatch.setattr("kam_market_ai.market_data.fubon_historical_contract_probe_cli.Settings.load", lambda path: object())
    monkeypatch.setattr("kam_market_ai.market_data.fubon_historical_contract_probe_cli.AuthorizationSettings.from_local_env", lambda path: object())
    code = main(["--live", "--env", "fixture.env"], bootstrap=Bootstrap(BootstrapResult(False, (), authorized)))
    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert payload["success"] is True
    assert payload["endpoint_invoked"] is False
    assert payload["trading_enabled"] is False
    assert history.calls == 0
