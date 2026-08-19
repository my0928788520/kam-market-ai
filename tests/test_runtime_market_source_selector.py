import importlib.util
from pathlib import Path

import pytest

from kam_market_ai.live_read_only.runtime_market_source import (
    RuntimeMarketSourceConfig,
    RuntimeMarketSourceError,
    RuntimeMarketSourceMode,
    RuntimeMarketSourceSelector,
)


def test_default_and_fake_live_are_explicit_and_read_only():
    selector = RuntimeMarketSourceSelector()
    offline = selector.select()
    fake = selector.select(RuntimeMarketSourceConfig(RuntimeMarketSourceMode.FAKE_LIVE))
    assert offline.mode is RuntimeMarketSourceMode.OFFLINE_DEMO and not offline.is_fake_live
    assert fake.is_fake_live and fake.provider.list_available_products() == ("MTX", "TMF", "TX")
    assert [fake.provider.read_snapshot(x).last_price for x in ("TX", "MTX", "TMF")]


def test_reserved_and_invalid_fail_closed():
    reserved = RuntimeMarketSourceSelector().select(
        RuntimeMarketSourceConfig(RuntimeMarketSourceMode.FUGLE_LIVE_RESERVED)
    )
    assert reserved.status.value == "RESERVED" and reserved.provider.list_available_products() == ()
    with pytest.raises(RuntimeMarketSourceError):
        RuntimeMarketSourceSelector().select(RuntimeMarketSourceConfig("bad"))  # type: ignore[arg-type]
    with pytest.raises(RuntimeMarketSourceError, match="FUBON_LIVE_CLIENT_REQUIRED"):
        RuntimeMarketSourceSelector().select(
            RuntimeMarketSourceConfig(RuntimeMarketSourceMode.FUBON_LIVE)
        )


def test_reserved_runtime_source_renders_fail_closed_header_and_preserves_drawer_safety():
    from kam_market_ai.paper_trading.operator_presenter import PaperTradingOperatorView
    from kam_market_ai.paper_trading.operator_wsgi import build_operator_wsgi

    reserved = (
        RuntimeMarketSourceSelector()
        .select(RuntimeMarketSourceConfig(RuntimeMarketSourceMode.FUGLE_LIVE_RESERVED))
        .provider
    )
    app = build_operator_wsgi(
        lambda: PaperTradingOperatorView("KAM", "", {}, {}, {"cash": "0"}, (), False),
        market_data_source=reserved,
    )
    html = b"".join(
        app({"REQUEST_METHOD": "GET", "PATH_INFO": "/", "QUERY_STRING": ""}, lambda *_: None)
    ).decode("utf-8")
    for text in (
        "真實行情來源尚未啟用",
        "資料不足／無法判讀",
        "帳戶未連線",
        "券商未連線",
        "唯讀模式",
        "禁止真實下單",
    ):
        assert text in html
    for text in ("買進", "賣出", "開倉", "加碼", "平倉", "可執行"):
        assert text not in html


def _operator_html_for(mode: RuntimeMarketSourceMode) -> str:
    from kam_market_ai.paper_trading.operator_presenter import PaperTradingOperatorView
    from kam_market_ai.paper_trading.operator_wsgi import build_operator_wsgi

    provider = RuntimeMarketSourceSelector().select(RuntimeMarketSourceConfig(mode)).provider
    app = build_operator_wsgi(
        lambda: PaperTradingOperatorView("KAM", "", {}, {}, {"cash": "0"}, (), False),
        market_data_source=provider,
    )
    return b"".join(
        app({"REQUEST_METHOD": "GET", "PATH_INFO": "/", "QUERY_STRING": ""}, lambda *_: None)
    ).decode("utf-8")


def test_reserved_source_renders_all_six_decision_blocks_fail_closed_without_demo_fallback():
    html = _operator_html_for(RuntimeMarketSourceMode.FUGLE_LIVE_RESERVED)

    for text in (
        "市場方向",
        "資料不足／無法判讀",
        "多空控制權",
        "不可判讀",
        "市場循環位置",
        "三週期狀態",
        "等待資料",
        "趨勢健康度",
        "唯一下一步",
        "等待資料恢復",
    ):
        assert text in html
    assert "離線示範行情｜" not in html
    assert "offline-demo" not in html
    for forbidden in ("買進", "賣出", "開倉", "加碼", "平倉", "可執行"):
        assert forbidden not in html


def test_runtime_headers_distinguish_offline_fake_live_ready_and_reserved_sources():
    offline_html = _operator_html_for(RuntimeMarketSourceMode.OFFLINE_DEMO)
    fake_html = _operator_html_for(RuntimeMarketSourceMode.FAKE_LIVE)
    reserved_html = _operator_html_for(RuntimeMarketSourceMode.FUGLE_LIVE_RESERVED)

    assert "離線示範行情" in offline_html
    assert "模擬即時行情｜WebSocket 模擬連線｜連線就緒" in fake_html
    assert "真實行情來源尚未啟用｜資料不足／無法判讀" in reserved_html
    assert "離線示範行情｜" not in fake_html
    assert "離線示範行情｜" not in reserved_html
    for html in (offline_html, fake_html, reserved_html):
        for safety_text in ("帳戶未連線", "券商未連線", "唯讀模式", "禁止真實下單"):
            assert safety_text in html


def _load_operator_cli_module():
    path = Path(__file__).parents[1] / "tools" / "run_paper_trading_operator.py"
    spec = importlib.util.spec_from_file_location("test_operator_cli", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_cli_parser_defaults_and_rejects_invalid_market_source():
    module = _load_operator_cli_module()
    parser = module.build_parser()
    assert module._empty_view().title == "KAM 交易決策操作台"
    assert parser.description == "本機唯讀 KAM 交易決策操作台"
    assert parser.parse_args([]).market_source == "offline-demo"
    assert parser.parse_args(["--market-source", "fake-live"]).market_source == "fake-live"
    assert parser.parse_args(["--market-source", "fugle-live"]).market_source == "fugle-live"
    assert parser.parse_args(["--market-source", "fubon-live"]).market_source == "fubon-live"
    with pytest.raises(SystemExit):
        parser.parse_args(["--market-source", "invalid-live"])


def test_cli_import_and_app_composition_do_not_connect_or_start_background_threads(monkeypatch):
    import socket
    import threading

    monkeypatch.setattr(
        socket, "create_connection", lambda *args, **kwargs: pytest.fail("socket connect")
    )
    monkeypatch.setattr(
        threading.Thread, "start", lambda *args, **kwargs: pytest.fail("thread start")
    )
    module = _load_operator_cli_module()
    app = module.build_operator_application(module.build_parser().parse_args([]))
    assert callable(app)


def test_cli_requires_explicit_live_flag_before_fubon_authorization():
    module = _load_operator_cli_module()
    args = module.build_parser().parse_args(["--market-source", "fubon-live"])
    with pytest.raises(RuntimeMarketSourceError, match="LIVE_FLAG_REQUIRED"):
        module.build_operator_application(args)


def test_cli_explicit_fubon_live_composes_started_source_and_cleanup(monkeypatch):
    module = _load_operator_cli_module()

    class Bootstrap:
        def run(self, settings, *, dry_run=True):
            assert not dry_run
            return type("Result", (), {"clients": object()})()

    class Discovery:
        def __init__(self, clients):
            assert clients is not None

        def resolve(self, *, after_hours=False):
            assert not after_hours
            return ("TX", "MTX", "TMF")

    class LiveClient:
        def __init__(self, clients, contracts):
            assert clients is not None and contracts == ("TX", "MTX", "TMF")
            self.connection_ready = False
            self.closed = False

        def start(self):
            self.connection_ready = True

        def fetch_latest(self, product_code):
            return None

        def list_products(self):
            return ()

        def close(self):
            self.closed = True
            self.connection_ready = False

    monkeypatch.setattr(module, "FubonFuturesContractDiscovery", Discovery)
    monkeypatch.setattr(module, "FubonFuturesLiveClient", LiveClient)
    args = module.build_parser().parse_args(
        ["--market-source", "fubon-live", "--live", "--env", "missing.env"]
    )
    app = module.build_operator_application(args, bootstrap=Bootstrap())

    assert callable(app)
    assert callable(app.close_market_data)
    app.close_market_data()


@pytest.mark.parametrize("flag", ["--demo", "--kam-rule-demo", None])
def test_cli_passes_selected_market_source_to_every_app_composition(monkeypatch, flag):
    module = _load_operator_cli_module()
    seen = []
    monkeypatch.setattr(
        module,
        "create_operator_app",
        lambda view, *, market_data_source: seen.append(market_data_source) or (lambda *_: ()),
    )
    if flag == "--demo":
        from kam_market_ai.paper_trading import operator_app

        monkeypatch.setattr(
            operator_app,
            "create_demo_operator_app",
            lambda *, market_data_source: seen.append(market_data_source) or (lambda *_: ()),
        )
    elif flag == "--kam-rule-demo":
        from kam_market_ai.paper_trading import operator_app

        monkeypatch.setattr(
            operator_app,
            "create_kam_rule_demo_operator_app",
            lambda *, market_data_source: seen.append(market_data_source) or (lambda *_: ()),
        )
    args = module.build_parser().parse_args(
        ([flag] if flag else []) + ["--market-source", "offline-demo"]
    )
    module.build_operator_application(args)
    assert len(seen) == (2 if flag else 1)
