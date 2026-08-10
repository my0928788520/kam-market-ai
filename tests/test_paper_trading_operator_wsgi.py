from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
import re

from kam_market_ai.paper_trading.operator_presenter import PaperTradingOperatorView
from kam_market_ai.paper_trading.operator_wsgi import build_operator_wsgi, render_account_html, render_operator_html
from kam_market_ai.paper_trading.demo_proposal import build_demo_session
from kam_market_ai.paper_trading.demo_snapshot import DEMO_SNAPSHOT
from kam_market_ai.paper_trading.operator_presenter import build_demo_operator_presenter
from kam_market_ai.live_read_only.market_snapshot import OFFLINE_DEMO_MARKET_DATA_SOURCE
from kam_market_ai.account_read_only import (
    AccountDataFreshness,
    AccountFunds,
    AccountPositionSummary,
    CapitalSafetyThresholds,
    DEMO_ACCOUNT_SOURCE,
    DemoAccountReadOnlySource,
    DemoMarginRequirementSource,
    FuturesAccountSnapshot,
    MarginRequirement,
    MarginUsage,
)


def _view() -> PaperTradingOperatorView:
    return PaperTradingOperatorView("<KAM>", "安全", {"instrument": "TEST"}, {"state": "等待中"}, {"cash": "100"}, (), False)


def test_wsgi_is_get_only_escapes_html_and_serves_static_css() -> None:
    app = build_operator_wsgi(_view); response = {}
    def start(status, headers): response.update(status=status, headers=headers)
    body = b"".join(app({"REQUEST_METHOD": "GET", "PATH_INFO": "/"}, start)).decode()
    assert response["status"] == "200 OK" and "&lt;KAM&gt;" in body and "lang='zh-Hant-TW'" in body
    assert "唯讀模式・禁止真實下單" in body and "Paper Order Proposal" not in body
    assert b"".join(app({"REQUEST_METHOD": "POST", "PATH_INFO": "/"}, start)) == "唯讀端點，不接受此操作。".encode("utf-8")
    assert response["status"] == "405 Method Not Allowed"
    assert b"body" in b"".join(app({"REQUEST_METHOD": "GET", "PATH_INFO": "/static/operator.css"}, start))
    assert "<KAM>" not in render_operator_html(_view())


def test_account_page_is_get_only_demo_data_and_never_exposes_trading_endpoints() -> None:
    app = build_operator_wsgi(_view)
    response = {}

    def start(status, headers):
        response.update(status=status, headers=headers)

    dashboard = b"".join(app({"REQUEST_METHOD": "GET", "PATH_INFO": "/"}, start)).decode()
    account = b"".join(app({"REQUEST_METHOD": "GET", "PATH_INFO": "/account"}, start)).decode()
    assert "id='account-drawer-trigger'" in dashboard and "期貨帳戶｜資金安全</button>" in dashboard
    assert response["status"] == "200 OK"
    for text in ("示範帳戶資料", "非真實帳戶", "唯讀模式", "禁止真實交易", "尚未連線"):
        assert text in account
    assert DEMO_ACCOUNT_SOURCE.snapshot.account_connected is False
    for status in ("帳戶未連線", "券商未連線", "交易功能停用", "禁止真實下單", "緊急停止"):
        assert status in account
    for internal_flag in ("account_connected=false", "live_order_allowed=false", "broker_connected=false", "trading_enabled=false"):
        assert internal_flag not in account
    assert "1,000,000" in account and "1000000" not in account
    b"".join(app({"REQUEST_METHOD": "POST", "PATH_INFO": "/account"}, start))
    assert response["status"] == "405 Method Not Allowed"
    b"".join(app({"REQUEST_METHOD": "GET", "PATH_INFO": "/account/order"}, start))
    assert response["status"] == "404 Not Found"


def test_account_page_calculates_all_position_margins_from_injected_read_only_source() -> None:
    timestamp = datetime(2026, 8, 5, tzinfo=UTC)
    snapshot = FuturesAccountSnapshot(
        "測試帳戶", "••••-1234",
        AccountFunds(Decimal("1000000"), Decimal("700000"), Decimal("1"), Decimal("0"), Decimal("1"), Decimal("0"), Decimal("0")),
        MarginUsage(Decimal("0")),
        (
            AccountPositionSummary("TX", "大台 TX", Decimal("1"), "LONG", Decimal("0")),
            AccountPositionSummary("MTX", "小台 MTX", Decimal("-2"), "SHORT", Decimal("0")),
            AccountPositionSummary("TMF", "微台 TMF", Decimal("3"), "LONG", Decimal("0")),
        ),
        "fixture-account", timestamp, AccountDataFreshness.FRESH, account_connected=True,
    )
    margin_source = DemoMarginRequirementSource((
        MarginRequirement("TX", Decimal("636000"), Decimal("488000"), timestamp, "fixture-margin", timestamp, AccountDataFreshness.FRESH),
        MarginRequirement("MTX", Decimal("159000"), Decimal("122000"), timestamp, "fixture-margin", timestamp, AccountDataFreshness.FRESH),
        MarginRequirement("TMF", Decimal("31800"), Decimal("24400"), timestamp, "fixture-margin", timestamp, AccountDataFreshness.FRESH),
    ))

    html = render_account_html(
        DemoAccountReadOnlySource(snapshot),
        CapitalSafetyThresholds(Decimal("0.5"), Decimal("0.75")),
        margin_source,
        selected_view="water-level",
    )

    assert "1,049,400" in html and "805,200" in html
    assert "fixture-margin" in html
    assert "詳細資料" in html


def test_account_center_get_tabs_detail_and_instrument_validation_are_fail_closed() -> None:
    app = build_operator_wsgi(_view)
    response = {}

    def start(status, headers):
        response.update(status=status, headers=headers)

    def get(query: str = "") -> str:
        return b"".join(app({"REQUEST_METHOD": "GET", "PATH_INFO": "/account", "QUERY_STRING": query}, start)).decode()

    overview = get()
    assert response["status"] == "200 OK"
    for label in ("帳戶總覽", "資金水位", "商品部位", "設定"):
        assert label in overview
    assert "全部持倉所需原始保證金" not in overview

    water = get("view=water-level")
    assert "全部持倉所需原始保證金" in water and "顯示詳細資料" in water
    assert "保證金詳細資料" not in water
    assert "保證金詳細資料" in get("view=water-level&detail=1")

    tmf = get("view=position")
    assert "契約代碼" in tmf and "TMF" in tmf
    assert "大台 TX" in tmf and "小台 MTX" in tmf and "微台 TMF" in tmf
    assert "商品代碼無效" in get("view=position&instrument=BAD")
    assert "檢視項目無效" in get("view=unsupported")
    for internal in ("account_connected=false", "live_order_allowed=false", "broker_connected=false", "trading_enabled=false"):
        assert internal not in overview


def test_account_center_localizes_visible_status_source_and_read_only_settings() -> None:
    html = render_account_html()
    visible = re.sub(r"\s(?:title|data-[\w-]+)='[^']*'", "", html)

    assert html.count("<section class='account-content'>") == 1
    assert "KAM 帳戶中心" in visible
    assert "離線示範帳戶快照" in visible
    assert "offline-demo-account-snapshot" not in visible
    assert "UNKNOWN" not in visible

    water = render_account_html(selected_view="water-level")
    visible_water = re.sub(r"\s(?:title|data-[\w-]+)='[^']*'", "", water)
    assert "資料不足／無法判讀" in visible_water
    assert "UNKNOWN" not in visible_water

    settings = render_account_html(selected_view="settings")
    for label in ("原始保證金倍數", "最低可用保證金", "最高資金使用率", "警示緩衝金額"):
        assert label in settings
    for key in ("initial_margin_multiplier", "minimum_free_margin", "maximum_margin_usage_ratio", "warning_buffer_amount"):
        assert key not in settings


def test_terminal_header_uses_read_only_market_snapshots_and_get_instrument_selector() -> None:
    app = build_operator_wsgi(_view)
    response = {}

    def start(status, headers):
        response.update(status=status, headers=headers)

    def get(query: str = "") -> str:
        return b"".join(app({"REQUEST_METHOD": "GET", "PATH_INFO": "/", "QUERY_STRING": query}, start)).decode()

    tmf = get()
    assert response["status"] == "200 OK"
    assert "TMF202610" in tmf and "24,108" in tmf and "82,514" in tmf
    assert "微型臺指期貨" in tmf and "休市" in tmf
    assert "微型臺指期貨・TMF｜TMF202610・202610｜最新 24,108・量 82,514" in tmf
    assert "資料時間：2026-08-06 02:14｜休市｜帳戶未連線・券商未連線・唯讀模式・禁止真實下單" in tmf
    assert "market-selector-chip active' href='/?instrument=TMF'" in tmf

    tx = get("instrument=TX")
    assert "TXF202609" in tx and "臺股期貨" in tx and "日盤" in tx and "14,872" in tx
    assert "market-selector-chip active' href='/?instrument=TX'" in tx
    mtx = get("instrument=MTX")
    assert "MXF202609" in mtx and "小型臺指期貨" in mtx and "夜盤" in mtx and "39,761" in mtx
    assert "market-selector-chip active' href='/?instrument=MTX'" in mtx

    invalid = get("instrument=BAD")
    assert "商品代碼無效" in invalid
    assert "TMF202610" not in invalid and "TXF202609" not in invalid and "MXF202609" not in invalid
    assert "未載入模擬委託建議" in invalid
    assert "account_connected=false" not in invalid and "broker_connected=false" not in invalid
    b"".join(app({"REQUEST_METHOD": "POST", "PATH_INFO": "/", "QUERY_STRING": "instrument=TX"}, start))
    assert response["status"] == "405 Method Not Allowed"


def test_terminal_account_drawer_is_closed_by_default_and_reuses_get_only_account_center() -> None:
    html = render_operator_html(_view())
    css = Path("src/kam_market_ai/paper_trading/static/operator.css").read_text(encoding="utf-8")

    assert "id='account-drawer-trigger'" in html
    assert "aria-expanded='false'" in html and "aria-controls='account-drawer'" in html
    assert "id='account-drawer'" in html and "role='dialog'" in html and "aria-modal='true'" in html
    assert "src='/account?view=overview'" in html
    for tab in ("帳戶總覽", "資金水位", "商品部位", "設定"):
        assert tab in html
    assert "開啟完整帳戶中心" in html and "href='/account'" in html
    assert "data-account-drawer-close" in html and "event.key==='Escape'" in html
    assert "trigger.focus()" in html
    for text in ("帳戶未連線", "券商未連線", "交易功能停用", "禁止真實下單", "緊急停止未啟動"):
        assert text in html
    assert "position: fixed" in css and "width: clamp(520px, 42vw, 720px)" in css
    assert "transform: translateX(102%)" in css and "transition: transform 190ms ease" in css
    assert "calc(100vw - 24px)" in css


def test_dashboard_renders_real_control_cells_and_coloured_cycle_structure() -> None:
    proposal, matching = build_demo_session()
    view = build_demo_operator_presenter(proposal, matching, DEMO_SNAPSHOT)
    html = render_operator_html(view, OFFLINE_DEMO_MARKET_DATA_SOURCE.read_snapshot("TX"))

    assert "多方 6｜空方 4" in html
    assert "多方 62" not in html and "空方 38" not in html
    assert "控制權分裂" in html
    assert html.count("class='control-cell ") == 10
    assert html.count("control-cell bull") == 6
    assert html.count("control-cell bear") == 4
    assert html.index("control-cell bear") > html.index("control-cell bull")
    assert "class='cycle-info'" in html
    assert "市場循環位置" in html
    assert "rise-path" in html and "fall-path" in html
    assert "linearGradient id='cycle-rise'" in html and "linearGradient id='cycle-fall'" in html
    assert "filter id='cycle-glow'" in html and "filter id='cycle-marker-glow'" in html
    assert "class='cycle-marker'" in html and "transform='translate(150 59)'" in html
    assert "preserveAspectRatio='xMidYMid meet'" in html
    for field in ("目前位置", "循環狀態", "上一階段", "下一階段", "唯一下一步", "風險"):
        assert field in html
    assert html.count("class='timeframe-card'") == 4
    assert "四週期狀態" in html
    for timeframe in ("週線", "日線", "60 分", "15 分"):
        assert timeframe in html
    assert "<b>5 分</b>" not in html
    assert len(view.demo["timeframes"]) == 5
    for footer_field in ("已實現損益", "未實現損益", "緊急停止"):
        assert footer_field in html
    for label in ("低檔確認", "起漲形成", "多方延伸", "高檔回落", "起跌形成", "空方延伸", "低點止跌"):
        assert label in html


def test_halted_and_closed_selected_snapshots_are_presented_fail_closed() -> None:
    proposal, matching = build_demo_session()
    view = build_demo_operator_presenter(proposal, matching, DEMO_SNAPSHOT)

    halted_html = render_operator_html(view, OFFLINE_DEMO_MARKET_DATA_SOURCE.read_snapshot("MTX"))
    assert "暫停／不可判讀" in halted_html
    assert "等待資料恢復" in halted_html
    assert "多方 6｜空方 4" not in halted_html
    assert halted_html.count("class='control-cell ") == 10

    closed_html = render_operator_html(view, OFFLINE_DEMO_MARKET_DATA_SOURCE.read_snapshot("TMF"))
    assert "休市／不可判讀" in closed_html
    assert "等待市場恢復" in closed_html
    assert "多方 6｜空方 4" not in closed_html
    assert closed_html.count("class='control-cell ") == 10


def test_desktop_layout_contract_prevents_page_scrolling_without_card_scrollers() -> None:
    css = Path("src/kam_market_ai/paper_trading/static/operator.css").read_text(encoding="utf-8")

    assert '@import "../../ui/design_tokens.css"' in css
    assert "height: 100vh" in css and "overflow: hidden" in css
    assert "grid-template-rows: minmax(160px, 205px) minmax(110px, 128px) minmax(96px, 110px) minmax(0, 1fr)" in css
    assert "footer { grid-row: 4; position: static;" in css
    assert ".cycle-chart svg" in css and "height: 180px" in css
    assert "marker-breathe 5s" in css
    assert ".proposal dd, .matching dd" in css and "text-overflow: ellipsis" in css
    assert "grid-template-columns: repeat(4, minmax(0, 1fr))" in css
    assert ".timeframes { grid-column: 1 / 3; grid-row: 2; padding: 8px 13px; }" in css
    assert ".timeframes h2 { margin-bottom: 5px; }" in css
    assert ".timeframe-card { padding: 5px 7px; overflow: hidden;" in css
    assert ".timeframe-card small { display: block; margin: 0;" in css
    assert ".trend-health-card { grid-column: 1; grid-row: 3; }" in css
    assert ".position-card { grid-column: 2; grid-row: 3; }" in css
    assert ".next-card { grid-column: 3; grid-row: 3;" in css
    assert ".control-cells-unscored" in css
    assert "@media (max-height: 650px) and (min-width: 1001px)" in css
    assert "grid-template-rows: minmax(130px, 150px) minmax(90px, 100px) minmax(78px, 88px) minmax(0, 1fr)" in css
    assert "justify-content: center" in css and "border-radius: 7px" in css
    bull_rule = css.split(".control-cell.bull", 1)[1].split(".control-cell.bear", 1)[0]
    bear_rule = css.split(".control-cell.bear", 1)[1]
    assert "#e63357" in bull_rule and "#b51f40" in bull_rule
    assert "#2fca9d" in bear_rule and "#19866e" in bear_rule
    assert "0 0 10px" in bull_rule and "0 3px 6px" not in bull_rule
    assert "transform: none" in css and "inset 0 -2px" not in css
    assert ".control-cell::before" not in css and ".control-cell::after" not in css
