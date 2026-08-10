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
        self.config = type("Config", (), {"base_url": "fixture"})()

    def request(self, method: str, path: str, **params: object) -> object:
        self.calls += 1
        raise AssertionError("probe must not invoke request")

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
    assert result.schema_version == "3.0"
    assert [item["name"] for item in result.candles_parameters] == ["symbol", "timeframe"]
    assert result.candles_parameters[0]["required"] == "true"
    assert len(result.fingerprint_sha256) == 64
    assert result.candles_evidence["qualname"].endswith("Historical.candles")
    assert result.candles_evidence["code_available"] is True
    assert result.request_evidence["parameters"][0]["name"] == "method"
    assert "base_url" in result.config_members
    assert result.candles_instructions


def test_probe_is_deterministic_and_contains_no_runtime_objects() -> None:
    first, _ = clients()
    second, _ = clients()
    left = probe_fubon_historical_contract(first).safe_payload()
    right = probe_fubon_historical_contract(second).safe_payload()
    assert left == right
    json.dumps(left)
    assert "password" not in json.dumps(left).lower()
    assert "account" not in json.dumps(left).lower()
    assert "fixture" not in json.dumps(left).lower()


def test_probe_fails_closed_when_candles_is_not_callable() -> None:
    authorized = AuthorizedMarketDataClients(
        WebSocket(),
        Rest(type("History", (), {"candles": 1, "request": lambda: None, "config": object()})()),
        WebSocket(),
        StockRest(),
    )
    try:
        probe_fubon_historical_contract(authorized)
    except HistoricalContractProbeError as error:
        assert str(error) == "CANDLES_NOT_CALLABLE"
    else:
        raise AssertionError("expected fail-closed error")


def test_probe_filters_code_strings_without_invoking_callable() -> None:
    class EvidenceHistorical(Historical):
        def candles(self, **params: object) -> object:
            endpoint = "/historical/candles/{symbol}"
            secret_label = "api_token"
            url = "https://marketdata.example.invalid"
            raise AssertionError((endpoint, secret_label, url, params))

    authorized, history = clients(EvidenceHistorical())
    result = probe_fubon_historical_contract(authorized)
    strings = result.candles_evidence["safe_code_strings"]
    assert history.calls == 0
    assert "/historical/candles/{symbol}" in strings
    assert "api_token" not in strings
    assert not any(value.startswith("https:") for value in strings)


def test_probe_records_sanitized_parameter_flow_without_secret_literals() -> None:
    class EvidenceHistorical(Historical):
        def candles(self, **params: object) -> object:
            symbol = params.pop("symbol")
            secret = "api_token"
            url = "https://marketdata.example.invalid"
            assert secret and url
            return self.request(f"historical/candles/{symbol}", **params)

    authorized, history = clients(EvidenceHistorical())
    result = probe_fubon_historical_contract(authorized)
    instructions = result.candles_instructions
    assert history.calls == 0
    assert any(item == {"opname": "LOAD_CONST", "safe_arg": "symbol"} for item in instructions)
    assert any(item == {"opname": "LOAD_FAST", "safe_arg": "params"} for item in instructions)
    assert any(item["opname"] in {"DICT_MERGE", "DICT_UPDATE"} for item in instructions)
    serialized = json.dumps(instructions)
    assert "api_token" not in serialized
    assert "marketdata.example.invalid" not in serialized


def test_probe_emits_no_instructions_when_callable_has_no_python_code() -> None:
    history = Historical()
    history.candles = len  # type: ignore[method-assign]
    authorized, _ = clients(history)
    result = probe_fubon_historical_contract(authorized)
    assert result.candles_instructions == ()


def test_probe_fails_closed_when_request_is_not_callable() -> None:
    history = Historical()
    history.request = 1  # type: ignore[method-assign]
    authorized, _ = clients(history)
    try:
        probe_fubon_historical_contract(authorized)
    except HistoricalContractProbeError as error:
        assert str(error) == "REQUEST_NOT_CALLABLE"
    else:
        raise AssertionError("expected fail-closed error")


def test_probe_never_serializes_config_values() -> None:
    authorized, _ = clients()
    payload = json.dumps(probe_fubon_historical_contract(authorized).safe_payload())
    assert "base_url" in payload
    assert "fixture" not in payload


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
