from datetime import UTC, datetime
from decimal import Decimal
from io import BytesIO
from pathlib import Path
import re

from kam_market_ai.paper_trading.operator_presenter import PaperTradingOperatorView
from kam_market_ai.paper_trading.operator_wsgi import _cycle, _paper_position_strip, _timeframe_card, build_operator_wsgi, render_account_html, render_help_html, render_operator_html
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
    assert ("Cache-Control", "no-store") in response["headers"]


def test_matching_margin_status_is_visually_emphasized() -> None:
    css = Path("src/kam_market_ai/paper_trading/static/operator.css").read_text(encoding="utf-8")

    assert ".matching h2 { margin-bottom: 3px; font-size: 14px; line-height: 1.1; }.matching dl { font-size: 13px; line-height: 1.4; }" in css
    assert ".matching h2 { margin-bottom: 1px; font-size: 13px; line-height: 1.05; }" in css
    assert ".matching dl dd:last-child { font-size: 14px; font-weight: 800; }" in css
    assert ".matching dl dd:last-child { font-size: 10.5px; }" in css
    assert ".matching dl { gap: 2px 10px; align-content: start; padding-block: 0; font-size: 10.5px; line-height: 1.2; }" in css
    assert ".performance-sample" in css
    assert "repeat(5, minmax(88px, 1fr))" in css
    assert "minmax(150px, 1.4fr)" in css
    assert ".performance-sample span" in css and "white-space: nowrap" in css
    assert ".matching:has(.performance-sample):has(> .footer-metrics)" in css
    assert "\\n.matching" not in css
    assert "border: 1px solid #b58a45" in css
    assert "grid-template-rows: auto auto minmax(0, 1fr) auto" in css
    assert ".matching:has(.performance-sample) .performance-sample { grid-column: 1 / -1; grid-row: 2;" in css
    assert ".matching:has(.performance-sample) > .footer-metrics { grid-column: 2; grid-row: 3;" in css
    assert ".matching:has(.performance-sample) .matching-status { grid-column: 1; grid-row: 3; grid-template-columns: max-content minmax(48px, .65fr) max-content minmax(156px, 1.65fr) max-content minmax(72px, .8fr);" in css
    assert ".matching:has(.performance-sample) > p { grid-column: 1 / -1; grid-row: 4;" in css
    assert "grid-template-columns: minmax(0, 1.55fr) minmax(250px, .85fr)" in css
    assert "grid-template-columns: repeat(2, minmax(0, 1fr))" in css
    assert "grid-auto-rows: min-content" in css
    assert ".performance-sample { grid-column: 1 / -1; grid-row: 2; grid-template-columns: auto repeat(4, minmax(0, 1fr));" in css
    assert ".performance-sample > b { grid-column: auto; font-size: 13px; }" in css
    assert ".performance-sample small { font-size: 11.5px; }" in css
    assert ".performance-sample strong { font-size: 14px; line-height: 1.25; }" in css
    assert "padding-left: 14px; font-size: 13px; line-height: 1.35;" in css
    html = render_operator_html(PaperTradingOperatorView(
        "<KAM>", "安全", {"instrument": "TEST"},
        {"目前契約": "TMFI6", "行情更新（台灣）": "2026-08-19 13:53:00", "Paper 持倉": "無持倉", "實盤狀態": "永久鎖定・禁止下單"},
        {"cash": "100"}, (), False,
    ))
    assert "<KAM>" not in html
    assert "class='matching-status'" in html
    assert "class='performance-sample'" in html
    assert "<small>進度</small>" in html
    assert "class='market-update-label'" in html
    assert "class='market-update-value'" in html
    assert "class='paper-position-label'" in html
    assert "class='paper-position-value'" in html
    assert "class='live-trading-status-label'" in html
    assert "class='live-trading-status-value' title='永久鎖定・禁止下單'>永久鎖定・禁止下單</dd>" in html
    assert ".matching-status .live-trading-status-value { grid-column: 2 / -1;" in css
    assert "minmax(156px, 1.65fr)" in css
    assert ".proposal .proposal-hash-label" in css
    assert ".matching .journal-validation-label" in css
    assert ".matching .journal-hash-value { display: none; }" in css


def test_operator_frontend_translates_internal_state_codes_to_chinese() -> None:
    card = _timeframe_card("60 分", "BD", {"status": "stale"})
    cycle = _cycle(PaperTradingOperatorView(
        "KAM", "安全", {}, {}, {}, (), False, demo={"u_stage": "U4"}
    ))

    assert ">BD<" not in card and "<strong>偏空</strong>" in card
    assert ">U4<" not in cycle and "class='cycle-code'>多方延伸後段<" in cycle


def test_paper_position_strip_emphasizes_active_profit_and_flat_waiting_state() -> None:
    active = _paper_position_strip(
        {"KAM 方向": "偏空", "模擬成交價": "44815"},
        {
            "Paper 持倉": "1 口・TMFI6",
            "停損／停利": "44535／44495",
            "目前模擬價": "44500",
            "未實現損益": "3150",
        },
    )
    flat = _paper_position_strip({"KAM 方向": "觀望"}, {"Paper 持倉": "無持倉"})

    assert "paper-position-profit" in active
    css = Path("src/kam_market_ai/paper_trading/static/operator.css").read_text(encoding="utf-8")
    assert ".paper-position-profit strong { color: #ffadbd; }" in css
    assert ".paper-position-risk strong { color: #8ff0c9; }" in css
    for value in ("偏空・1 口・TMFI6", "44815", "44500", "44535", "44495", "3150"):
        assert value in active
    assert "paper-position-flat" in flat
    assert "目前無模擬持倉" in flat and "等待 KAM 條件完整" in flat


def test_matching_shortens_journal_hash_without_losing_full_tooltip() -> None:
    full_hash = "6be8f7e52ac49a77a7d7773f7a27fed41ac6999d2d00360e92c3fd262332137f"
    view = PaperTradingOperatorView(
        "KAM",
        "安全",
        {},
        {"日誌雜湊": full_hash},
        {"cash": "100"},
        (),
        False,
    )

    html = render_operator_html(view)

    assert f"title='{full_hash}'" in html
    assert "6be8f7e52ac4…</dd>" in html
    assert f">{full_hash}</dd>" not in html


def test_current_analysis_uses_free_matching_space_and_stable_refresh_hash() -> None:
    demo = {
        "instrument": "TMF",
        "source_kind": "FUBON_LIVE_FIVE_TIMEFRAME",
        "current_analysis": {
            "headline": "中期偏多、短線尚未同步，維持觀望",
            "basis": "日線在60MA上方、60分20MA支撐未破、60分偏多",
            "conflict": "5分與15分尚未同步轉強",
            "waiting_for": "等待15分與5分完成多方確認",
            "risk": "60分有效跌破20MA則注意轉弱",
            "fingerprint": "abc123",
            "bucket": "2026-08-17T08:00:00+00:00",
        },
    }
    view = PaperTradingOperatorView(
        "KAM",
        "安全",
        {},
        {"LINE 通知": "已啟用"},
        {"cash": "100"},
        (),
        False,
        demo=demo,
    )
    html = render_operator_html(view)
    css = Path("src/kam_market_ai/paper_trading/static/operator.css").read_text(
        encoding="utf-8"
    )
    refresh = Path(
        "src/kam_market_ai/paper_trading/static/dashboard-refresh.js"
    ).read_text(encoding="utf-8")

    assert "<h2>現況分析</h2>" not in html
    assert "data-analysis-hash='abc123'" not in html
    assert "即時盤勢判讀" not in html
    assert ".current-analysis-summary" in css
    assert ".timeframes > h2, .current-analysis-summary > b { display: none; }" in css
    assert ".timeframes { grid-template-rows: minmax(0, 1fr); }" in css
    assert "font-size: 14px" in css
    assert "class='current-analysis-details'" not in html
    assert ".proposal { grid-column: 1; grid-row: 3 / 5; }" in css
    assert ".matching { grid-column: 2 / 4; grid-row: 3 / 5; }" in css
    assert "currentCard.dataset.analysisHash === nextCard.dataset.analysisHash" in refresh
    assert "nextDetails.replaceWith(currentDetails)" not in refresh


def test_local_session_switch_post_is_explicit_and_redirects_to_charts() -> None:
    calls = []
    app = build_operator_wsgi(
        _view,
        session_switcher=lambda value: (calls.append(value) is None, "已切換"),
    )
    response = {}
    body = b"session=afterhours&instrument=TMF&timeframe=15m"
    result = b"".join(app({
        "REQUEST_METHOD": "POST",
        "PATH_INFO": "/session-switch",
        "CONTENT_LENGTH": str(len(body)),
        "wsgi.input": BytesIO(body),
    }, lambda status, headers: response.update(status=status, headers=dict(headers))))

    assert calls == ["afterhours"]
    assert response["status"] == "303 See Other"
    assert response["headers"]["Location"] == (
        "/charts?instrument=TMF&timeframe=15m&session_notice=ok"
    )
    assert result.decode() == "已切換"



def test_local_session_switch_redirect_rejects_untrusted_chart_context() -> None:
    app = build_operator_wsgi(
        _view,
        session_switcher=lambda _value: (False, "新時段資料驗證失敗，已維持原時段"),
    )
    response = {}
    body = b"session=invalid&instrument=%2Faccount&timeframe=bad"

    result = b"".join(app({
        "REQUEST_METHOD": "POST",
        "PATH_INFO": "/session-switch",
        "CONTENT_LENGTH": str(len(body)),
        "wsgi.input": BytesIO(body),
    }, lambda status, headers: response.update(status=status, headers=dict(headers))))

    assert response["status"] == "303 See Other"
    assert response["headers"]["Location"] == (
        "/charts?instrument=TMF&timeframe=60m&session_notice=failed"
    )
    assert result.decode() == "新時段資料驗證失敗，已維持原時段"


def test_help_page_contains_sop_horizons_rollover_and_risk_boundaries() -> None:
    html = render_help_html()
    assert "<html class='help-page'" in html and "<body class='help-page'>" in html
    assert "KAM 是交易決策作業系統，不是承諾獲利的交易指示工具" in html
    assert "當前是否具備交易條件，以及下一步應採取什麼行動" in html
    assert "喊單工具" not in html
    assert "後端可以複雜" not in html
    for text in (
        "每日使用 SOP", "週期與預期持有時間", "長週期", "中期波段", "當沖",
        "第三個星期三", "到期前 5 個營業日開始提醒", "不是交易所強制換倉日",
        "禁止真實自動下單", "風險聲明",
    ):
        assert text in html
    response = {}
    body = b"".join(
        build_operator_wsgi(_view)(
            {"REQUEST_METHOD": "GET", "PATH_INFO": "/help"},
            lambda status, headers: response.update(status=status, headers=headers),
        )
    ).decode()
    assert response["status"] == "200 OK" and "KAM 使用說明｜SOP" in body
    assert "大台 TX" in body and "每點 200 元" in body and "701,000 元" in body
    assert "小台 MTX" in body and "每點 50 元" in body and "175,250 元" in body
    assert "微台 TMF" in body and "每點 10 元" in body and "35,050 元" in body


def test_help_page_uses_document_flow_instead_of_dashboard_grid() -> None:
    css = Path("src/kam_market_ai/paper_trading/static/operator.css").read_text(encoding="utf-8")
    assert "html.help-page, body.help-page" in css
    assert ".help-main { display: block;" in css


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

    margin_detail = render_account_html(selected_view="water-level", detail=True)
    assert "TMF：原始 35,050／維持 26,900" in margin_detail
    assert "期交所 2026-08-12 股價指數類保證金" in margin_detail

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
    assert "<span class='header-market-status'>資料時間（台灣）：2026-08-06 10:14｜休市｜資料新鮮｜帳戶未連線・券商未連線・唯讀模式・禁止真實下單</span>" in tmf
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


def test_wsgi_serves_non_overlapping_dashboard_refresh_script() -> None:
    app = build_operator_wsgi(_view)
    response = {}
    start = lambda status, headers: response.update(status=status, headers=headers)

    script = b"".join(
        app(
            {"REQUEST_METHOD": "GET", "PATH_INFO": "/static/dashboard-refresh.js"},
            start,
        )
    ).decode()

    assert response["status"] == "200 OK"
    assert ("Content-Type", "text/javascript; charset=utf-8") in response["headers"]
    assert "fetch(window.location.href" in script
    assert "window.setTimeout(refreshDashboard, REFRESH_INTERVAL_MS)" in script
    assert "refreshInFlight" in script
    assert '".dashboard"' in script and '"main > footer"' in script
    assert "if (!current && !replacement) continue" in script


def test_market_status_time_is_explicitly_converted_to_taipei() -> None:
    tmf = OFFLINE_DEMO_MARKET_DATA_SOURCE.read_snapshot("TMF")
    html = render_operator_html(_view(), tmf)

    assert "資料時間（台灣）：2026-08-06 10:14" in html
    assert "資料時間：2026-08-06 02:14" not in html


def test_market_time_is_in_header_and_latest_snapshot_line_is_emphasized() -> None:
    html = render_operator_html(_view(), OFFLINE_DEMO_MARKET_DATA_SOURCE.read_snapshot("TMF"))
    css = Path("src/kam_market_ai/paper_trading/static/operator.css").read_text(encoding="utf-8")

    header_end = html.index("</header>")
    banner_start = html.index("<div class='banner market-status-line'")
    assert html.index("class='header-market-status'") < header_end < banner_start
    assert "資料時間（台灣）：" not in html[banner_start:html.index("</div>", banner_start)]
    assert ".market-status-line { display: flex; align-items: center;" in css
    assert "font-size: 13px; font-weight: 750;" in css


def test_terminal_account_drawer_is_closed_by_default_and_reuses_get_only_account_center() -> None:
    html = render_operator_html(_view())
    css = Path("src/kam_market_ai/paper_trading/static/operator.css").read_text(encoding="utf-8")

    assert "id='account-drawer-trigger'" in html
    assert "aria-expanded='false'" in html and "aria-controls='account-drawer'" in html
    assert "id='account-drawer'" in html and "role='dialog'" in html and "aria-modal='true'" in html
    assert "src='/account/embed?view=overview'" in html
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
    assert "grid-template-rows: 68px 38px minmax(0, 1fr) auto" in css
    assert ".account-drawer-footer { display: grid; grid-template-columns: repeat(5, max-content);" in css
    assert ".account-drawer-footer a { grid-column: 1 / -1; justify-self: end; margin-left: 0;" in css
    assert ".account-main { height: 100vh; grid-template-rows: 48px 32px 34px minmax(0, 1fr) auto;" in css
    assert ".account-content { min-height: 0; overflow-x: hidden; overflow-y: auto;" in css
    assert ".account-status-footer { grid-row: 5; display: flex; flex-wrap: wrap;" in css
    assert ".account-status-footer span { flex: 0 0 auto; white-space: nowrap; }" in css
    assert ".account-embedded .account-main { grid-template-rows: minmax(0, 1fr);" in css
    assert ".account-embedded .account-main > header" in css


def test_unknown_cycle_does_not_place_current_marker_on_a_market_stage() -> None:
    view = PaperTradingOperatorView(
        "KAM",
        "安全",
        {},
        {},
        {},
        (),
        False,
        demo={"source_kind": "FUBON_LIVE_FIVE_TIMEFRAME", "u_stage": "U0"},
    )

    html = render_operator_html(
        view,
        OFFLINE_DEMO_MARKET_DATA_SOURCE.read_snapshot("TX"),
    )

    assert "class='cycle-position-pending'" in html
    assert ">等待位置判讀</text>" in html
    assert "class='cycle-marker'" not in html
    assert "class='cycle-current-label'" not in html


def test_embedded_account_center_hides_duplicate_chrome_and_preserves_navigation() -> None:
    embedded = render_account_html(selected_view="position", selected_instrument="TMF", embedded=True)
    full = render_account_html(selected_view="position", selected_instrument="TMF")

    assert "<body class='account-embedded'>" in embedded
    assert "href='/account/embed?view=position&amp;instrument=TX'" in embedded
    assert "class='account-content account-position-view'" in embedded
    assert "<body class='account-embedded'>" not in full
    assert "href='/account/embed?view=position&amp;instrument=TX'" not in full

    app = build_operator_wsgi(_view)
    response = {}
    body = b"".join(app({"REQUEST_METHOD": "GET", "PATH_INFO": "/account/embed", "QUERY_STRING": "view=position&instrument=TMF"}, lambda status, headers: response.update(status=status, headers=headers))).decode()
    assert response["status"] == "200 OK"
    assert "<body class='account-embedded'>" in body


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
    assert "class='cycle-current-label'" in html and ">目前位置</text>" in html
    assert "class='cycle-position-pending'" not in html
    assert "preserveAspectRatio='xMidYMid meet'" in html
    for field in ("目前位置", "循環狀態", "上一階段", "下一階段", "下一步", "風險"):
        assert field in html
    assert html.count("class='timeframe-card'") == 3
    assert "<strong>ND</strong>" not in html
    assert "三週期狀態" in html
    for timeframe in ("日線", "60 分", "15 分"):
        assert timeframe in html
    assert "<b>週線</b>" not in html
    assert "<b>5 分</b>" not in html
    assert len(view.demo["timeframes"]) == 5
    for footer_field in ("已實現損益", "未實現損益", "緊急停止"):
        assert footer_field in html
    for disclaimer_text in (
        "僅供研究、模擬與決策輔助",
        "不構成投資建議、獲利保證或代客操作",
        "模擬績效不代表未來結果",
        "可能產生超過原始保證金之損失",
        "交易結果與損益由使用者自行承擔",
    ):
        assert disclaimer_text in html
    assert html.count("<span>風險聲明：") == 1
    assert "中斷。</span><span>期貨具高槓桿" in html
    for label in ("低檔確認", "起漲形成", "多方延伸", "高檔回落", "起跌形成", "空方延伸", "低點止跌"):
        assert label in html


def test_dashboard_reference_prices_use_standard_half_up_integer_rounding() -> None:
    view = PaperTradingOperatorView(
        "KAM",
        "安全",
        {},
        {},
        {},
        (),
        False,
        demo={
            "current_price": 45895.5,
            "timeframe_details": {
                "週線": {
                    "last_price": 45895.5,
                    "ma20": 45895.5,
                    "price_vs_ma20": "equal",
                    "ma20_direction": "flat",
                }
            },
        },
    )

    html = render_operator_html(view)

    assert html.count("45,896") >= 2
    assert "45,895.50" not in html


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
    assert "grid-template-columns: 1fr 1fr 1.35fr" in css
    assert "grid-template-rows: minmax(126px, 132px) minmax(184px, 192px) minmax(96px, 110px) minmax(0, 1fr)" in css
    assert "footer { grid-row: 4; position: static;" in css
    assert ".risk-disclaimer" in css and ".footer-metrics" in css
    assert "font-size: 11px" in css and ".risk-disclaimer span { display: block; }" in css
    assert ".cycle-card { grid-column: 3; grid-row: 1 / 3; display: grid;" in css
    assert ".cycle-chart svg" in css and "height: 230px" in css
    assert ".cycle-stage-label" in css and "font-size: 10.5px" in css
    assert ".cycle-info dt" in css and "font-size: 12px" in css
    assert ".cycle-market-current dd" in css and "#8ff0db" in css
    assert ".cycle-market-resistance dd" in css and "#ff9eb2" in css
    assert ".cycle-market-support dd" in css and "#82e4bd" in css
    assert "marker-breathe 5s" in css
    assert ".proposal, .matching { display: flex; flex-direction: column; padding: 13px 16px; }" in css
    assert ".proposal p, .matching p" in css and "font-size: 13px" in css
    assert ".proposal dl, .matching dl" in css and "align-content: center" in css
    assert ".proposal dd, .matching dd" in css and "text-overflow: ellipsis" in css
    assert ".matching > .footer-metrics" in css
    assert ".timeframes > div { display: grid; min-height: 0; grid-template-columns: repeat(3, minmax(0, 1fr));" in css
    assert ".cycle-weekly-pill text { font-size: 13.5px; }" in css
    assert ".cycle-card-body { grid-template-columns: minmax(0, 1.18fr) minmax(260px, 1.22fr); gap: 5px; }" in css
    assert ".cycle-info .cycle-next-step dd { overflow: visible;" in css
    assert "transform='translate({pill_x} -18)'" in Path("src/kam_market_ai/paper_trading/operator_wsgi.py").read_text(encoding="utf-8")
    assert ".timeframes { grid-column: 1 / 3; grid-row: 2; display: grid; grid-template-rows: auto minmax(0, 1fr);" in css
    assert ".timeframes h2 { margin-bottom: 7px; color: #f5f8ff; font-size: 16px;" in css
    assert ".timeframes > div { display: grid; min-height: 0;" in css
    assert ".timeframe-card { display: flex; flex-direction: column; justify-content: center; padding: 9px 11px;" in css
    assert ".timeframe-card small { display: block; margin: 2px 0 0;" in css
    assert ".timeframe-card b { display: block; color: #f8fbff; font-size: 18px;" in css
    assert ".timeframe-card strong { font-size: 26px;" in css
    assert ".timeframe-card span { display: block; color: #ffffff; font-size: 13px;" in css
    assert ".timeframe-resistance" in css and ".timeframe-support" in css
    assert ".chart-overlay-line[hidden] { display: none; }" in css
    assert ".trend-health-card { display: none; }" in css
    assert ".direction-card { grid-template-columns: minmax(0, 1fr); grid-template-rows: auto auto minmax(0, 1fr); row-gap: 4px; }" in css
    assert ".direction-card strong { align-self: end; font-size: 20px; line-height: 22px; }" in css
    assert ".direction-card p { align-self: start; margin: 0; font-size: 12px; font-weight: 650; line-height: 16px; }" in css
    assert ".position-card { grid-column: 1; grid-row: 3; display: grid;" in css
    assert "grid-template-columns: repeat(2, minmax(0, 1fr))" in css
    assert ".position-card p { grid-column: 2; grid-row: 2; align-self: center; justify-self: start;" in css
    assert "color: #ff5d72" in css and "font-weight: 900" in css
    assert "text-shadow: 0 0 12px #ff304f66" in css
    assert ".next-card { grid-column: 2 / 4; grid-row: 3; display: grid;" in css
    assert ".control-cells-unscored" in css
    assert ".control-cell.unconfirmed" in css
    assert "@media (max-height: 1000px) and (min-width: 1001px)" in css
    assert "@media (max-height: 820px) and (min-width: 1001px)" not in css
    assert ".matching { min-height: 170px; }" not in css
    assert "grid-template-rows: 30px 30px minmax(0, 1fr) 44px" in css
    assert "grid-template-rows: 76px 130px 90px minmax(106px, 1fr)" in css
    assert ".current-analysis-summary { gap: 1px 8px; padding-left: 12px; }" in css
    assert ".cycle-chart svg { height: 108px; min-height: 108px; }" in css
    assert ".proposal { padding-bottom: 4px; }.matching { overflow: hidden; }" in css
    assert "footer { gap: 2px; padding: 4px 9px; }" in css
    assert "grid-template-rows: 68px 142px 70px minmax(0, 1fr)" in css
    assert ".trend-health-card strong, .position-card strong { font-size: 24px; line-height: 1.05; }" in css
    assert ".position-card p { margin: 0; font-size: 14px; font-weight: 850; line-height: 1.1; }" in css
    assert ".proposal { grid-column: 1; grid-row: 4; }" in css
    assert ".matching { grid-column: 2 / 4; grid-row: 4; }" in css
    assert ".proposal dl { grid-template-columns: max-content minmax(0, 1fr); }" in css
    assert ".matching dl { grid-template-columns: repeat(2" in css
    assert ".banner-message { min-width: 0; overflow: hidden; text-overflow: ellipsis; }" in css
    assert ".line-alert-chip { display: flex; flex: 0 0 auto;" in css
    assert "margin-left: auto" in css and "border: 1px solid #b58a45" in css
    assert ".line-alert-chip strong { color: #fff7df; font-size: 12px; font-weight: 850;" in css
    assert ".proposal .live-order-status-value" in css and "white-space: nowrap" in css
    assert ".proposal .live-order-status-value { grid-column: 2 / -1;" in css
    assert ".proposal .simulation-status-label, .proposal .blocking-reason-label" in css
    assert "margin-left: 16px" in css
    assert "grid-template-columns: max-content minmax(0, 1.2fr) max-content minmax(0, 1fr)" in css
    assert ".proposal dd { overflow: visible; white-space: normal; overflow-wrap: anywhere;" in css
    assert ".proposal .live-order-status-value { padding-bottom: 2px; font-size: 11.5px; line-height: 1.3; }" in css
    assert ".proposal { padding-bottom: 5px; }" in css
    assert "justify-content: center" in css and "border-radius: 7px" in css
    bull_rule = css.split(".control-cell.bull", 1)[1].split(".control-cell.bear", 1)[0]
    bear_rule = css.split(".control-cell.bear", 1)[1]
    assert "#e63357" in bull_rule and "#b51f40" in bull_rule
    assert "#2fca9d" in bear_rule and "#19866e" in bear_rule
    assert "0 0 10px" in bull_rule and "0 3px 6px" not in bull_rule
    assert "transform: none" in css and "inset 0 -2px" not in css
    assert ".control-cell::before" not in css and ".control-cell::after" not in css
