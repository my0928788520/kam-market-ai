from pathlib import Path

import tomllib

from kam_market_ai.market_data.fubon_live_five_timeframe_dashboard_cli import (
    build_local_dashboard_router,
    build_parser,
)


ROOT = Path(__file__).parents[1]


def test_installed_commands_include_live_read_only_workflows() -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))

    assert project["project"]["scripts"]["kam-fubon-dashboard"].endswith(
        "fubon_live_five_timeframe_dashboard_cli:main"
    )
    assert project["project"]["scripts"]["kam-fubon-five-timeframe"].endswith(
        "fubon_live_five_timeframe_verifier_cli:main"
    )


def test_dashboard_parser_keeps_browser_launch_explicit_and_local() -> None:
    args = build_parser().parse_args([])
    assert args.host == "127.0.0.1"
    assert args.symbol is None
    assert args.open_browser is False

    args = build_parser().parse_args(["--symbol", "TMFH6", "--open-browser"])
    assert args.open_browser is True


def test_live_dashboard_opens_the_established_operator_homepage() -> None:
    source = (
        ROOT
        / "src"
        / "kam_market_ai"
        / "market_data"
        / "fubon_live_five_timeframe_dashboard_cli.py"
    ).read_text(encoding="utf-8")

    assert 'webbrowser.open(f"http://{args.host}:{args.port}/")' in source
    assert '"url": f"http://{args.host}:{args.port}/"' in source


def test_live_dashboard_routes_operator_styles_and_tools_to_operator_app() -> None:
    calls = []

    def operator(environ, start_response):
        calls.append(("operator", environ["PATH_INFO"]))
        return [b"operator"]

    def diagnostic(environ, start_response):
        calls.append(("diagnostic", environ["PATH_INFO"]))
        return [b"diagnostic"]

    app = build_local_dashboard_router(operator, diagnostic)
    for path in ("/", "/static/operator.css", "/account", "/charts", "/help"):
        assert app({"PATH_INFO": path}, lambda *_args: None) == [b"operator"]
    for path in ("/five-timeframe", "/api/five-timeframe", "/static/dashboard.css"):
        assert app({"PATH_INFO": path}, lambda *_args: None) == [b"diagnostic"]

    assert ("operator", "/static/operator.css") in calls


def test_windows_launcher_preserves_read_only_local_boundary() -> None:
    source = (ROOT / "tools" / "start_fubon_five_timeframe_dashboard.ps1").read_text(
        encoding="utf-8"
    )

    assert source.isascii()

    source = source.lower()

    assert "--live" in source
    assert "127.0.0.1" in source
    assert "--open-browser" in source
    assert "$env:pythonpath" in source
    assert "'src'" in source
    assert "[parameter(mandatory = $true)]" not in source
    assert "place_order" not in source
    assert "0.0.0.0" not in source
    assert "git push" not in source
