"""GET-only local WSGI dashboard renderer."""
from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from html import escape
from pathlib import Path
from typing import Callable, Iterable
from urllib.parse import parse_qs

from kam_market_ai.live_read_only.market_snapshot import (
    DEFAULT_MARKET_PRODUCT,
    OFFLINE_DEMO_MARKET_DATA_SOURCE,
    MarketDataReadOnlySource,
    MarketSnapshot,
    MarketSnapshotStatus,
)
from kam_market_ai.live_read_only.decision_presentation import SelectedSnapshotDecisionPresenter

from kam_market_ai.account_read_only import (
    AccountReadOnlySource, CapitalSafetyAssessment, CapitalSafetyThresholds,
    DEMO_ACCOUNT_SOURCE, DEMO_ACCOUNT_THRESHOLDS, DEMO_MARGIN_SOURCE,
    MarginRequirementSource, assess_capital_safety, calculate_required_margins,
)
from .operator_presenter import PaperTradingOperatorView

_STAGES = (("位置不明", "資料不足"), ("低檔築底", "低檔確認"), ("起漲形成", "多方建立"), ("多方延伸初期", "趨勢延伸中"), ("多方延伸後段", "高檔回落"), ("高檔過熱", "過熱警戒"), ("起跌形成", "結構轉弱"), ("空方延伸", "空方延伸中"), ("低檔止跌", "低檔確認"))
_POINTS = ((24,142),(58,129),(104,91),(150,59),(198,48),(246,61),(292,91),(336,127),(376,146))

def _stage_index(value: object) -> int:
    text = str(value)
    return min(8, int(text[1])) if len(text) > 1 and text[:1] == "U" and text[1].isdigit() else 0

def _cells(view: PaperTradingOperatorView) -> tuple[int, str]:
    try:
        bull = int(round(float((view.demo or {}).get("bull_score", 50)) / 10))
    except (TypeError, ValueError):
        bull = 5
    bull = max(0, min(10, bull))
    return bull, "".join(f"<span class='control-cell {'bull' if item < bull else 'bear'}' aria-hidden='true'></span>" for item in range(10))

def _cycle(view: PaperTradingOperatorView) -> str:
    """Render the complete, read-only MarketCycleCard from existing view data."""
    demo = view.demo or {}
    raw = str(demo.get("u_stage", "U0"))
    index = _stage_index(raw)
    x, y = _POINTS[index]
    stage, state = _STAGES[index]
    if demo.get("cycle_label") is not None:
        stage = str(demo["cycle_label"])
        state = str(demo["cycle_label"])
    previous = _STAGES[max(0, index - 1)][0]
    following = _STAGES[min(8, index + 1)][0]
    next_step = str(demo.get("next_step", "等待資料完整"))
    risk = "偏高" if index >= 5 else "風險受控"
    labels = (
        ("低檔確認", 30, 164), ("起漲形成", 96, 79), ("多方延伸", 156, 30),
        ("高檔回落", 229, 74), ("起跌形成", 275, 105), ("空方延伸", 329, 151), ("低點止跌", 367, 169),
    )
    stage_labels = "".join(
        f"<text class='cycle-stage-label' x='{px}' y='{py}'>{label}</text>"
        for label, px, py in labels
    )
    return f"""
    <section class='cycle-card' aria-label='市場循環位置（倒 U 階段）'>
      <header class='cycle-card-header'>
        <div><h2>市場循環位置</h2><small class='cycle-code'>{escape(raw[:2])}</small></div>
        <span class='cycle-badge'>規則性</span>
      </header>
      <div class='cycle-card-body'>
        <div class='cycle-chart'>
          <svg viewBox='0 0 400 180' width='100%' height='100%' preserveAspectRatio='xMidYMid meet' role='img' aria-label='完整市場循環曲線'>
            <defs>
              <linearGradient id='cycle-rise' x1='0%' y1='100%' x2='100%' y2='0%'><stop offset='0%' stop-color='#ff91b1'/><stop offset='43%' stop-color='#ff315e'/><stop offset='78%' stop-color='#ff553e'/><stop offset='100%' stop-color='#fff4d0'/></linearGradient>
              <linearGradient id='cycle-fall' x1='0%' y1='0%' x2='100%' y2='100%'><stop offset='0%' stop-color='#fff4d0'/><stop offset='38%' stop-color='#7cf09c'/><stop offset='68%' stop-color='#35df8e'/><stop offset='100%' stop-color='#24d4cc'/></linearGradient>
              <filter id='cycle-glow' x='-20%' y='-35%' width='140%' height='170%'><feGaussianBlur stdDeviation='3.6' result='blur'/><feMerge><feMergeNode in='blur'/><feMergeNode in='SourceGraphic'/></feMerge></filter>
              <filter id='cycle-marker-glow' x='-120%' y='-120%' width='340%' height='340%'><feGaussianBlur stdDeviation='6' result='blur'/><feMerge><feMergeNode in='blur'/><feMergeNode in='SourceGraphic'/></feMerge></filter>
            </defs>
            <path class='cycle-path rise-path' d='M24 142 Q42 140 58 129 Q81 111 104 91 Q127 75 150 59 Q174 45 198 48' fill='none' stroke='url(#cycle-rise)' stroke-width='7' stroke-linecap='round' filter='url(#cycle-glow)'/>
            <path class='cycle-path fall-path' d='M198 48 Q222 50 246 61 Q269 79 292 91 Q314 111 336 127 Q356 140 376 146' fill='none' stroke='url(#cycle-fall)' stroke-width='7' stroke-linecap='round' filter='url(#cycle-glow)'/>
            <circle class='cycle-peak-glow' cx='198' cy='48' r='7'/>
            {stage_labels}
            <g class='cycle-marker' transform='translate({x} {y})' filter='url(#cycle-marker-glow)'><circle class='marker-outer' r='15'/><circle class='marker-inner-ring' r='9'/><circle class='marker-core' r='4'/></g>
          </svg>
        </div>
        <dl class='cycle-info'>
          <div><dt>目前位置</dt><dd>{escape(stage)}</dd></div>
          <div><dt>循環狀態</dt><dd>{escape(state)}</dd></div>
          <div><dt>上一階段</dt><dd>{escape(previous)}</dd></div>
          <div><dt>下一階段</dt><dd>{escape(following)}</dd></div>
          <div><dt>唯一下一步</dt><dd>{escape(next_step)}</dd></div>
          <div><dt>風險</dt><dd>{risk}</dd></div>
        </dl>
      </div>
      <p class='cycle-note'>倒 U 為市場位置判讀，不是價格預測。</p>
    </section>"""

def _rows(values: dict[str, str]) -> str:
    return "".join(f"<dt>{escape(key.replace('_', ' '))}</dt><dd title='{escape(str(value))}'>{escape(str(value)[:10]) if key.endswith('hash') else escape(str(value))}</dd>" for key, value in values.items())


def _timeframe_card(name: object, state: object) -> str:
    """Apply a compact, presentation-only vocabulary to existing timeframe values."""
    raw = str(state)
    code, interpretation = {
        "偏多": ("AU", "多方健康"),
        "整理": ("NF", "整理"),
        "等待確認": ("NF", "等待確認"),
        "觀望": ("NU", "觀望"),
        "偏空": ("BD", "空方健康"),
    }.get(raw, ("—", raw))
    return (
        "<article class='timeframe-card'>"
        f"<b>{escape(str(name))}</b><strong>{code}</strong><span>{escape(interpretation)}</span>"
        "<small>價格相對 20MA：—</small><small>20MA 方向：—</small></article>"
    )


def _frontend_timeframe_cards(timeframes: Iterable[tuple[object, object]]) -> str:
    """Keep 5-minute data available to rules while omitting its dashboard card."""
    return "".join(
        _timeframe_card(name, state)
        for name, state in timeframes
        if str(name) != "5 分"
    )


def render_operator_html(view: PaperTradingOperatorView) -> str:
    demo = view.demo or {}; bull, cells = _cells(view)
    frames = _frontend_timeframe_cards(demo.get("timeframes", ()))
    audit = "".join(f"<li title='{escape(item['hash'])}'>{escape(item['type'])} · {escape(item['hash'][:10])}</li>" for item in view.audit_events[-3:])
    return f"""<!doctype html><html lang='zh-Hant-TW'><head><meta charset='utf-8'><title>{escape(view.title)}</title><link rel='stylesheet' href='/static/operator.css'></head><body><main><header><h1>{escape(view.title)}</h1><span>{escape(str(demo.get('instrument', '—')))}</span><span>資料狀態：{'DEMO' if demo else '本機'}</span><span>PAPER TRADING</span><span>唯讀模式・模擬執行・禁止真實下單</span></header><div class='banner'>{escape(str(demo.get('banner', '尚未載入模擬委託建議。本機頁面目前為唯讀模式。')))}</div><div class='dashboard'><section class='direction-card'><h2>市場方向</h2><strong>{escape(str(demo.get('direction', '—')))}</strong><p>{escape(str(demo.get('direction_reason', '尚未載入方向資料')))}</p></section><section class='control-card'><h2>多空控制權</h2><strong>多方 {bull}｜空方 {10-bull}</strong><small>控制權分裂</small><div class='control-cells'>{cells}</div></section>{_cycle(view)}<section class='timeframes'><h2>四週期狀態</h2><div>{frames}</div></section><section><h2>趨勢健康度</h2><strong>{escape(str(demo.get('trend_health', '—')))}</strong></section><section><h2>目前模擬部位</h2><strong>{escape(str(demo.get('position', '無部位')))}</strong><p>現價 {escape(str(demo.get('current_price', '—')))} · 未實現 {escape(str(demo.get('unrealized_pnl', '—')))}</p></section><section class='next-card next-wait'><h2>唯一下一步</h2><strong>{escape(str(demo.get('next_step', '等待資料完整')))}</strong></section><section class='proposal'><h2>模擬委託建議</h2><dl>{_rows(view.proposal)}</dl></section><section class='matching'><h2>模擬撮合結果</h2><dl>{_rows(view.matching)}</dl></section></div><footer><span>模擬現金：{escape(str(view.ledger.get('cash', '—')))}</span><span>模擬部位：{escape(str(view.ledger.get('positions', '—')))}</span><span>已實現損益：—</span><span>未實現損益：{escape(str(demo.get('unrealized_pnl', '—')))}</span><span>緊急停止：{'已啟動' if view.emergency_stop else '未啟動'}</span><span class='audit'>稽核紀錄：{audit}</span></footer></main></body></html>"""

def _money(value: object) -> str:
    if value is None:
        return "—"
    if isinstance(value, (int, float, Decimal)):
        return f"{value:,}"
    return str(value)


def render_account_html(source: AccountReadOnlySource = DEMO_ACCOUNT_SOURCE, thresholds: CapitalSafetyThresholds = DEMO_ACCOUNT_THRESHOLDS, margin_source: MarginRequirementSource = DEMO_MARGIN_SOURCE) -> str:
    """Render the isolated local account viewer; no request can mutate account state."""
    snapshot = source.read_snapshot()
    assessment: CapitalSafetyAssessment = assess_capital_safety(snapshot, thresholds, margin_source)
    positions = {position.product_code: position for position in snapshot.positions}
    calculated_margins = calculate_required_margins(snapshot.positions, margin_source)
    required_initial, required_maintenance = calculated_margins or (None, None)
    requirements = margin_source.read_requirements()
    margin_effective_at = assessment.margin_effective_at or (min(item.effective_at for item in requirements) if requirements else None)
    margin_source_name = assessment.margin_source or ", ".join(sorted({item.source for item in requirements}))
    margin_details = "".join(
        f"<li>{escape(item.product_code)}：原始 {_money(item.initial_margin)}／維持 {_money(item.maintenance_margin)} · 生效 {escape(str(item.effective_at))} · {escape(item.source)} · {escape(item.freshness.value)}</li>"
        for item in margin_source.read_requirements()
    )

    def position_row(code: str, label: str) -> str:
        position = positions.get(code)
        if position is None:
            return f"<article><h3>{label}</h3><p>資料不足</p></article>"
        side = escape(position.side or "無部位")
        return f"<article><h3>{escape(position.label)}</h3><strong>{side} × {_money(position.quantity)}</strong><p>未實現損益：{_money(position.unrealized_pnl)}</p></article>"

    safety_label = {"SAFE": "安全", "CAUTION": "注意", "DANGER": "危險", "UNKNOWN": "資料不足／無法判讀"}[assessment.level.value]
    return f"""<!doctype html><html lang='zh-Hant-TW'><head><meta charset='utf-8'><title>期貨帳戶｜資金安全</title><link rel='stylesheet' href='/static/operator.css'></head><body><main class='account-main'>
      <header><h1>期貨帳戶｜資金安全</h1><a class='account-chip' href='/'>返回市場儀表板</a><span>唯讀模式・禁止真實交易</span></header>
      <div class='account-banner'>示範帳戶資料・非真實帳戶・禁止真實交易</div>
      <section class='account-overview'><div><h2>帳戶狀態</h2><strong>{escape(snapshot.account_status)}</strong><p>帳戶：{escape(snapshot.account_masked)}</p></div><div class='safety-{assessment.level.value.lower()}'><h2>資金安全水位</h2><strong>{safety_label}</strong><p>{escape(assessment.reason)}</p></div><div><h2>資料來源</h2><strong>{escape(snapshot.source)}</strong><p>唯讀帳戶檢視</p></div></section>
      <section class='account-funds'><h2>資金水位</h2><div class='account-metrics'><article><span>帳戶權益數</span><strong>{_money(snapshot.funds.equity)}</strong></article><article><span>可動用保證金</span><strong>{_money(snapshot.funds.available_margin)}</strong></article><article><span>全部部位所需原始保證金</span><strong>{_money(required_initial)}</strong></article><article><span>全部部位所需維持保證金</span><strong>{_money(required_maintenance)}</strong></article><article><span>資金使用率</span><strong>{_money(assessment.usage_ratio)}</strong></article><article><span>距離警戒水位</span><strong>{_money(assessment.distance_to_caution)}</strong></article></div></section>
      <section class='account-details'><article><span>距離危險水位</span><strong>{_money(assessment.distance_to_danger)}</strong></article><article><span>未實現損益</span><strong>{_money(snapshot.funds.unrealized_pnl)}</strong></article><article><span>今日已實現損益</span><strong>{_money(snapshot.funds.today_realized_pnl)}</strong></article><article><span>警示原因</span><strong>{escape(assessment.reason)}</strong></article><article><span>保證金生效日期／來源</span><strong>{escape(str(margin_effective_at or '—'))} · {escape(margin_source_name or '—')}</strong></article><article><span>最後更新／資料新鮮度</span><strong>{escape(str(snapshot.updated_at or '—'))} · {escape(snapshot.freshness.value)}</strong></article><details class='account-margin-details'><summary>詳細資料</summary><ul>{margin_details}</ul></details></section>
      <section class='account-positions'><h2>三類期貨部位摘要</h2><div>{position_row('TX', '大台 TX')}{position_row('MTX', '小台 MTX')}{position_row('TMF', '微台 TMF')}</div></section>
      <footer class='account-status-footer'><span>帳戶未連線</span><span>券商未連線</span><span>交易功能停用</span><span>禁止真實下單</span><span>緊急停止：{'已啟動' if snapshot.emergency_stop else '未啟動'}</span></footer>
    </main></body></html>"""


def render_operator_html(view: PaperTradingOperatorView) -> str:
    """Render the market dashboard and expose only a GET link to /account."""
    demo = view.demo or {}
    bull, cells = _cells(view)
    frames = _frontend_timeframe_cards(demo.get("timeframes", ()))
    audit = "".join(f"<li title='{escape(item['hash'])}'>{escape(item['type'])} · {escape(item['hash'][:10])}</li>" for item in view.audit_events[-3:])
    return f"""<!doctype html><html lang='zh-Hant-TW'><head><meta charset='utf-8'><title>{escape(view.title)}</title><link rel='stylesheet' href='/static/operator.css'></head><body><main><header><h1>{escape(view.title)}</h1><a class='account-chip' href='/account'>期貨帳戶｜資金安全</a><span>{escape(str(demo.get('instrument', '—')))}</span><span>資料狀態：{'DEMO' if demo else '本機'}</span><span>PAPER TRADING</span><span>唯讀模式・模擬執行・禁止真實下單</span></header><div class='banner'>{escape(str(demo.get('banner', '尚未載入模擬委託建議。本機頁面目前為唯讀模式。')))}</div><div class='dashboard'><section class='direction-card'><h2>市場方向</h2><strong>{escape(str(demo.get('direction', '—')))}</strong><p>{escape(str(demo.get('direction_reason', '尚未載入方向資料')))}</p></section><section class='control-card'><h2>多空控制權</h2><strong>多方 {bull}｜空方 {10-bull}</strong><small>控制權分裂</small><div class='control-cells'>{cells}</div></section>{_cycle(view)}<section class='timeframes'><h2>四週期狀態</h2><div>{frames}</div></section><section><h2>趨勢健康度</h2><strong>{escape(str(demo.get('trend_health', '—')))}</strong></section><section><h2>目前模擬部位</h2><strong>{escape(str(demo.get('position', '無部位')))}</strong><p>現價 {escape(str(demo.get('current_price', '—')))} · 未實現 {escape(str(demo.get('unrealized_pnl', '—')))}</p></section><section class='next-card next-wait'><h2>唯一下一步</h2><strong>{escape(str(demo.get('next_step', '等待資料完整')))}</strong></section><section class='proposal'><h2>模擬委託建議</h2><dl>{_rows(view.proposal)}</dl></section><section class='matching'><h2>模擬撮合結果</h2><dl>{_rows(view.matching)}</dl></section></div><footer><span>模擬現金：{escape(str(view.ledger.get('cash', '—')))}</span><span>模擬部位：{escape(str(view.ledger.get('positions', '—')))}</span><span>已實現損益：—</span><span>未實現損益：{escape(str(demo.get('unrealized_pnl', '—')))}</span><span>緊急停止：{'已啟動' if view.emergency_stop else '未啟動'}</span><span class='audit'>稽核紀錄：{audit}</span></footer></main></body></html>"""


_ACCOUNT_TABS = (("overview", "帳戶總覽"), ("water-level", "資金水位"), ("position", "商品部位"), ("settings", "設定"))
_ACCOUNT_DISPLAY_TEXT = {
    "UNKNOWN": "資料不足／無法判讀",
    "SAFE": "安全",
    "CAUTION": "注意",
    "DANGER": "危險",
    "DEMO": "示範資料",
    "offline-demo-account-snapshot": "離線示範帳戶快照",
    "offline-demo-margin-snapshot": "離線示範保證金快照",
}


def _account_metric(label: str, value: object) -> str:
    raw = _money(value)
    display = _ACCOUNT_DISPLAY_TEXT.get(raw, raw)
    return f"<article class='account-metric'><span>{escape(label)}</span><strong title='{escape(raw)}'>{escape(display)}</strong></article>"


def render_account_html(source: AccountReadOnlySource = DEMO_ACCOUNT_SOURCE, thresholds: CapitalSafetyThresholds = DEMO_ACCOUNT_THRESHOLDS, margin_source: MarginRequirementSource = DEMO_MARGIN_SOURCE, *, selected_view: str = "overview", selected_instrument: str = "TMF", detail: bool = False) -> str:
    """GET-only Account Center rendered exclusively from immutable read-only sources."""
    snapshot = source.read_snapshot()
    assessment = assess_capital_safety(snapshot, thresholds, margin_source)
    requirements = {item.product_code: item for item in margin_source.read_requirements()}
    calculated = calculate_required_margins(snapshot.positions, margin_source)
    initial, maintenance = calculated or (None, None)
    tabs = "".join(f"<a class='account-tab {'active' if key == selected_view else ''}' href='/account?view={key}'>{label}</a>" for key, label in _ACCOUNT_TABS)
    grid = lambda values: "<div class='account-grid'>" + "".join(_account_metric(label, value) for label, value in values) + "</div>"
    if selected_view not in {key for key, _ in _ACCOUNT_TABS}:
        content = "<section class='account-content account-invalid'><h2>檢視項目無效</h2><p>請選擇有效的帳戶檢視。</p></section>"
    elif selected_view == "overview":
        content = "<section class='account-content'><h2>帳戶總覽</h2>" + grid((("帳戶狀態", snapshot.account_status), ("帳戶權益數", snapshot.funds.equity), ("可動用保證金", snapshot.funds.available_margin), ("今日已實現損益", snapshot.funds.today_realized_pnl), ("未實現損益", snapshot.funds.unrealized_pnl), ("資料來源", snapshot.source), ("最後更新", snapshot.updated_at), ("資料新鮮度", snapshot.freshness.value))) + "</section>"
    elif selected_view == "water-level":
        effective = assessment.margin_effective_at or min((item.effective_at for item in requirements.values()), default=None)
        source_name = assessment.margin_source or ", ".join(sorted({item.source for item in requirements.values()}))
        safety = _ACCOUNT_DISPLAY_TEXT[assessment.level.value]
        values = (("帳戶權益", snapshot.funds.equity), ("全部持倉所需原始保證金", initial), ("全部持倉所需維持保證金", maintenance), ("可動用保證金", snapshot.funds.available_margin), ("資金使用率", assessment.usage_ratio), ("距離警戒水位", assessment.distance_to_caution), ("距離危險水位", assessment.distance_to_danger), ("警示原因", assessment.reason), ("保證金資料來源", source_name), ("生效日期", effective), ("新鮮度", snapshot.freshness.value))
        if detail:
            items = "".join(f"<li title='{escape(item.source)}'>{escape(item.product_code)}：原始 {_money(item.initial_margin)}／維持 {_money(item.maintenance_margin)} · {escape(str(item.effective_at))} · {escape(_ACCOUNT_DISPLAY_TEXT.get(item.source, item.source))} · {escape(_ACCOUNT_DISPLAY_TEXT.get(item.freshness.value, item.freshness.value))}</li>" for item in sorted(requirements.values(), key=lambda item: item.product_code))
            extra = f"<aside class='account-detail-panel'><h3>保證金詳細資料</h3><ul>{items}</ul><a href='/account?view=water-level'>收起詳細資料</a></aside>"
        else:
            extra = "<a class='account-detail-link' href='/account?view=water-level&amp;detail=1'>顯示詳細資料</a>"
        content = f"<section class='account-content account-water-view'><h2>資金水位</h2><div class='water-level safety-{assessment.level.value.lower()}'><strong>{safety}</strong><span>{escape(assessment.reason)}</span></div>" + grid(values) + extra + "</section>"
    elif selected_view == "position" and selected_instrument not in {"TX", "MTX", "TMF"}:
        content = "<section class='account-content account-invalid'><h2>商品代碼無效</h2><p>請使用 TX、MTX 或 TMF。</p></section>"
    elif selected_view == "position":
        position = next((item for item in snapshot.positions if item.product_code == selected_instrument), None)
        requirement = requirements.get(selected_instrument)
        switcher = "".join(f"<a class='instrument-tab {'active' if code == selected_instrument else ''}' href='/account?view=position&amp;instrument={code}'>{label}</a>" for code, label in (("TX", "大台 TX"), ("MTX", "小台 MTX"), ("TMF", "微台 TMF")))
        values = (("商品名稱", position.label if position else "資料不足"), ("契約代碼", selected_instrument), ("部位方向", position.side if position and position.side else "無部位"), ("口數", position.quantity if position else None), ("均價", position.average_price if position else None), ("現價", position.market_price if position else None), ("未實現損益", position.unrealized_pnl if position else None), ("使用保證金", snapshot.funds.used_margin), ("原始保證金", requirement.initial_margin if requirement else None), ("維持保證金", requirement.maintenance_margin if requirement else None), ("最後更新", snapshot.updated_at))
        content = "<section class='account-content account-position-view'><h2>商品部位</h2><nav class='instrument-tabs'>" + switcher + "</nav>" + grid(values) + "</section>"
    else:
        content = "<section class='account-content account-settings-view'><h2>唯讀設定</h2>" + grid((("原始保證金倍數", thresholds.initial_margin_multiplier), ("最低可用保證金", thresholds.minimum_free_margin), ("最高資金使用率", thresholds.maximum_margin_usage_ratio), ("警示緩衝金額", thresholds.warning_buffer_amount), ("安全門檻來源", "注入式唯讀設定"), ("設定版本", "KAM 帳戶中心 V1"))) + "</section>"
    account = "帳戶已連線" if snapshot.account_connected else "帳戶未連線"
    broker = "券商已連線" if snapshot.broker_connected else "券商未連線"
    emergency = "緊急停止已啟動" if snapshot.emergency_stop else "緊急停止未啟動"
    return f"""<!doctype html><html lang='zh-Hant-TW'><head><meta charset='utf-8'><title>KAM 帳戶中心</title><link rel='stylesheet' href='/static/operator.css'></head><body><main class='account-main'><header><div><h1>KAM 帳戶中心</h1><small>期貨帳戶｜資金安全</small></div><a class='account-chip' href='/'>返回市場儀表板</a><span>唯讀模式・禁止真實交易</span></header><div class='account-banner'>示範帳戶資料・非真實帳戶・唯讀模式・禁止真實交易</div><nav class='account-tabs' aria-label='帳戶檢視'>{tabs}</nav>{content}<footer class='account-status-footer'><span>{account}</span><span>{broker}</span><span>交易功能停用</span><span>禁止真實下單</span><span>{emergency}</span></footer></main></body></html>"""


def _market_snapshot_header(snapshot: MarketSnapshot) -> str:
    session = {"DAY": "日盤", "NIGHT": "夜盤", "CLOSED": "休市", "UNKNOWN": "資料不足／無法判讀"}[snapshot.trading_session.value]
    freshness = {"FRESH": "資料新鮮", "STALE": "資料延遲", "EXPIRED": "資料過期", "UNKNOWN": "資料不足／無法判讀"}[snapshot.freshness.value]
    market = {"OPEN": "交易中", "HALTED": "暫停交易", "CLOSED": "休市", "UNKNOWN": "資料不足／無法判讀"}.get(snapshot.market_status, snapshot.market_status)
    selected = snapshot.product_code
    selector = "".join(
        f"<a class='market-selector-chip {'active' if code == selected else ''}' href='/?instrument={code}'>{label}</a>"
        for code, label in (("TX", "大台 TX"), ("MTX", "小台 MTX"), ("TMF", "微台 TMF"))
    )
    return f"<div class='market-selector' aria-label='商品切換'>{selector}</div>"
    if snapshot.status is MarketSnapshotStatus.INVALID_PRODUCT:
        fields = "<span class='market-invalid'>商品代碼無效</span>"
    else:
        fields = "".join((
            f"<span class='market-chip'>{escape(snapshot.instrument_name)} · {escape(snapshot.product_code)}</span>",
            f"<span class='market-chip'>{escape(snapshot.contract_code or '—')}／{escape(snapshot.contract_month or '—')}</span>",
            f"<span class='market-chip'>最新：{escape(_money(snapshot.last_price))} · 量：{escape(_money(snapshot.volume))}</span>",
            f"<span class='market-chip'>資料時間：{escape(str(snapshot.timestamp or '—'))}</span>",
            f"<span class='market-chip'>{session} · {market} · {freshness}</span>",
            "<span class='market-chip' title='OFFLINE_DEMO'>離線示範行情</span>",
        ))
    return f"<div class='market-selector' aria-label='商品切換'>{selector}</div><div class='market-snapshot-fields'>{fields}</div>"


def render_operator_html(view: PaperTradingOperatorView, snapshot: MarketSnapshot | None = None) -> str:
    """Render existing terminal cards plus a read-only market snapshot header only."""
    snapshot = snapshot or OFFLINE_DEMO_MARKET_DATA_SOURCE.read_snapshot(DEFAULT_MARKET_PRODUCT)
    demo = view.demo or {}
    bull, cells = _cells(view)
    frames = _frontend_timeframe_cards(demo.get("timeframes", ()))
    audit = "".join(f"<li title='{escape(item['hash'])}'>{escape(item['type'])} · {escape(item['hash'][:10])}</li>" for item in view.audit_events[-3:])
    proposal = "<section class='proposal'><h2>模擬委託建議</h2><dl>{}</dl></section>".format(_rows(view.proposal))
    if snapshot.status is MarketSnapshotStatus.INVALID_PRODUCT:
        proposal = "<section class='proposal'><h2>模擬委託建議</h2><p>商品代碼無效，未載入模擬委託建議。</p></section>"
    return f"""<!doctype html><html lang='zh-Hant-TW'><head><meta charset='utf-8'><title>{escape(view.title)}</title><link rel='stylesheet' href='/static/operator.css'></head><body><main><header><h1>{escape(view.title)}</h1><a class='account-chip' href='/account'>期貨帳戶｜資金安全</a>{_market_snapshot_header(snapshot)}<span class='header-readonly-note'>帳戶未連線・券商未連線・唯讀模式・模擬執行・禁止真實下單</span></header><div class='banner'>{escape(str(demo.get('banner', '尚未載入模擬委託建議。本機頁面目前為唯讀模式。')))} · 目前僅 Header 已切換至離線示範行情；決策卡尚未接入此商品 snapshot。</div><div class='dashboard'><section class='direction-card'><h2>市場方向</h2><strong>{escape(str(demo.get('direction', '—')))}</strong><p>{escape(str(demo.get('direction_reason', '尚未載入方向資料')))}</p></section><section class='control-card'><h2>多空控制權</h2><strong>多方 {bull}｜空方 {10-bull}</strong><small>控制權分裂</small><div class='control-cells'>{cells}</div></section>{_cycle(view)}<section class='timeframes'><h2>四週期狀態</h2><div>{frames}</div></section><section><h2>趨勢健康度</h2><strong>{escape(str(demo.get('trend_health', '—')))}</strong></section><section><h2>目前模擬部位</h2><strong>{escape(str(demo.get('position', '無部位')))}</strong><p>現價 {escape(str(demo.get('current_price', '—')))} · 未實現 {escape(str(demo.get('unrealized_pnl', '—')))}</p></section><section class='next-card next-wait'><h2>唯一下一步</h2><strong>{escape(str(demo.get('next_step', '等待資料完整')))}</strong></section>{proposal}<section class='matching'><h2>模擬撮合結果</h2><dl>{_rows(view.matching)}</dl></section></div><footer><span>模擬現金：{escape(str(view.ledger.get('cash', '—')))}</span><span>模擬部位：{escape(str(view.ledger.get('positions', '—')))}</span><span>已實現損益：—</span><span>未實現損益：{escape(str(demo.get('unrealized_pnl', '—')))}</span><span>緊急停止：{'已啟動' if view.emergency_stop else '未啟動'}</span><span class='audit'>稽核紀錄：{audit}</span></footer></main></body></html>"""


_render_terminal_html = render_operator_html


def _market_status_line(snapshot: MarketSnapshot) -> str:
    if snapshot.status is MarketSnapshotStatus.INVALID_PRODUCT:
        return "商品代碼無效｜帳戶未連線・券商未連線・唯讀模式・禁止真實下單"
    session = {"DAY": "日盤", "NIGHT": "夜盤", "CLOSED": "休市", "UNKNOWN": "資料不足／無法判讀"}[snapshot.trading_session.value]
    return f"{snapshot.instrument_name}・{snapshot.product_code}｜{snapshot.contract_code}・{snapshot.contract_month}｜最新 {_money(snapshot.last_price)}・量 {_money(snapshot.volume)}<br>資料時間：{str(snapshot.timestamp or '—')[:16].replace('T', ' ')}｜{session}｜帳戶未連線・券商未連線・唯讀模式・禁止真實下單"


def _account_drawer_html() -> str:
    return """<div class='account-drawer-backdrop' data-account-drawer-close hidden></div><aside id='account-drawer' class='account-drawer' role='dialog' aria-modal='true' aria-labelledby='account-drawer-title' aria-hidden='true'><header class='account-drawer-header'><div><h2 id='account-drawer-title'>期貨帳戶｜資金安全</h2><p>示範帳戶・唯讀模式・禁止真實交易</p></div><button type='button' class='account-drawer-close' data-account-drawer-close aria-label='關閉帳戶抽屜'>關閉</button></header><nav class='account-drawer-tabs' aria-label='帳戶檢視'><a href='/account?view=overview' target='account-drawer-frame'>帳戶總覽</a><a href='/account?view=water-level' target='account-drawer-frame'>資金水位</a><a href='/account?view=position&amp;instrument=TMF' target='account-drawer-frame'>商品部位</a><a href='/account?view=settings' target='account-drawer-frame'>設定</a></nav><iframe class='account-drawer-frame' name='account-drawer-frame' title='KAM 帳戶中心唯讀內容' src='/account?view=overview'></iframe><footer class='account-drawer-footer'><span>帳戶未連線</span><span>券商未連線</span><span>交易功能停用</span><span>禁止真實下單</span><span>緊急停止未啟動</span><a href='/account'>開啟完整帳戶中心</a></footer></aside><script>(function(){const trigger=document.getElementById('account-drawer-trigger'),drawer=document.getElementById('account-drawer'),backdrop=document.querySelector('.account-drawer-backdrop'),close=()=>{drawer.classList.remove('is-open');drawer.setAttribute('aria-hidden','true');backdrop.hidden=true;trigger.setAttribute('aria-expanded','false');trigger.focus()},open=()=>{drawer.classList.add('is-open');drawer.setAttribute('aria-hidden','false');backdrop.hidden=false;trigger.setAttribute('aria-expanded','true');drawer.querySelector('.account-drawer-close').focus()};trigger.addEventListener('click',()=>drawer.classList.contains('is-open')?close():open());document.querySelectorAll('[data-account-drawer-close]').forEach(item=>item.addEventListener('click',close));document.addEventListener('keydown',event=>{if(event.key==='Escape'&&drawer.classList.contains('is-open'))close()})})();</script>"""


def render_operator_html(view: PaperTradingOperatorView, snapshot: MarketSnapshot | None = None) -> str:
    """Add a client-only Account Drawer around the existing read-only terminal."""
    snapshot = snapshot or OFFLINE_DEMO_MARKET_DATA_SOURCE.read_snapshot(DEFAULT_MARKET_PRODUCT)
    presentation = SelectedSnapshotDecisionPresenter().present(snapshot, view.demo)
    demo = dict(view.demo or {})
    bull_cells = presentation.control.bull_score
    demo.update({"direction": presentation.direction.label, "direction_reason": presentation.direction.reason, "bull_score": bull_cells * 10 if bull_cells is not None else 50, "cycle_label": presentation.cycle.label, "trend_health": presentation.trend_health.label, "next_step": presentation.next_step.label, "timeframes": tuple((item.timeframe, item.label) for item in presentation.timeframes), "u_stage": "U0" if presentation.cycle.state in {"closed", "halted", "invalid"} else "U3"})
    html = _render_terminal_html(replace(view, demo=demo), snapshot)
    trigger = "<button id='account-drawer-trigger' class='account-chip account-drawer-trigger' type='button' aria-expanded='false' aria-controls='account-drawer'>期貨帳戶｜資金安全</button>"
    html = html.replace("<a class='account-chip' href='/account'>期貨帳戶｜資金安全</a>", trigger, 1)
    html = html.replace("<span class='header-readonly-note'>帳戶未連線・券商未連線・唯讀模式・模擬執行・禁止真實下單</span>", "", 1)
    banner_start = html.index("<div class='banner'>")
    banner_end = html.index("</div>", banner_start) + len("</div>")
    html = html[:banner_start] + f"<div class='banner market-status-line' title='OFFLINE_DEMO'>離線示範行情｜{_market_status_line(snapshot)}</div>" + html[banner_end:]
    html = html.replace("<h2>模擬委託建議</h2>", "<h2>模擬委託建議</h2><p>決策呈現已切換；模擬委託流程尚未接入此商品 snapshot。</p>", 1)
    html = html.replace("<h2>模擬撮合結果</h2>", "<h2>模擬撮合結果</h2><p>決策呈現已切換；模擬委託流程尚未接入此商品 snapshot。</p>", 1)
    return html.replace("</main></body>", _account_drawer_html() + "</main></body>", 1)


def build_operator_wsgi(view_provider: Callable[[], PaperTradingOperatorView], account_source: AccountReadOnlySource = DEMO_ACCOUNT_SOURCE, account_thresholds: CapitalSafetyThresholds = DEMO_ACCOUNT_THRESHOLDS, margin_source: MarginRequirementSource = DEMO_MARGIN_SOURCE, market_data_source: MarketDataReadOnlySource = OFFLINE_DEMO_MARKET_DATA_SOURCE, public_embed_config=None) -> Callable[..., Iterable[bytes]]:
    from kam_market_ai.live_read_only.decision_presentation import SelectedSnapshotDecisionPresenter
    from kam_market_ai.live_read_only.runtime_market_source import RuntimeMarketSourceStatus
    from kam_market_ai.paper_trading.embed_presenter import EmbedPagePresenter
    from kam_market_ai.paper_trading.public_routes import build_health_response
    from kam_market_ai.public_deployment import PublicEmbedConfig
    public_embed_config = public_embed_config or PublicEmbedConfig()
    css_path = Path(__file__).with_name("static") / "operator.css"
    def app(environ: dict[str, object], start_response: Callable[..., object]) -> Iterable[bytes]:
        path, method = str(environ.get("PATH_INFO", "/")), str(environ.get("REQUEST_METHOD", "GET"))
        headers = [("Content-Security-Policy", public_embed_config.content_security_policy), ("X-Content-Type-Options", "nosniff"), ("Referrer-Policy", "strict-origin-when-cross-origin"), ("Permissions-Policy", "geolocation=(), camera=(), microphone=()"), ("Cache-Control", "no-store")]
        if path == "/healthz" and method == "GET":
            response = build_health_response(); body = response.body.encode()
            start_response("200 OK", [("Content-Type", response.content_type), *headers]); return [body]
        if path == "/readyz" and method == "GET":
            ready = str(getattr(market_data_source, "status", "READY")) == "READY" and str(getattr(market_data_source, "mode", "offline-demo")) != "fugle-live"
            body = (b'{"status":"ready","source_mode":"offline-demo","trading_enabled":false}' if ready else b'{"status":"not_ready","trading_enabled":false}')
            start_response("200 OK" if ready else "503 Service Unavailable", [("Content-Type", "application/json; charset=utf-8"), *headers]); return [body]
        if method != "GET":
            start_response("405 Method Not Allowed", [("Content-Type", "text/plain; charset=utf-8"), ("Allow", "GET")]); return ["唯讀端點，不接受此操作。".encode()]
        if path == "/static/operator.css":
            start_response("200 OK", [("Content-Type", "text/css; charset=utf-8")]); return [css_path.read_bytes()]
        if path == "/embed":
            if not public_embed_config.enable_embed:
                start_response("404 Not Found", [("Content-Type", "text/plain; charset=utf-8"), *headers]); return [b"Not found"]
            query = parse_qs(str(environ.get("QUERY_STRING", "")), keep_blank_values=True)
            selected = query.get("instrument", [DEFAULT_MARKET_PRODUCT])[0]
            snapshot = market_data_source.read_snapshot(selected)
            decision = SelectedSnapshotDecisionPresenter().present(snapshot)
            runtime_status = getattr(market_data_source, "status", RuntimeMarketSourceStatus.READY)
            model = EmbedPagePresenter().build_model(snapshot, decision, runtime_status, public_embed_config, selected, public_embed_config.enable_account_drawer)
            body = EmbedPagePresenter().render(model).encode()
            start_response("200 OK", [("Content-Type", "text/html; charset=utf-8"), *headers]); return [body]
        if path == "/account":
            query = parse_qs(str(environ.get("QUERY_STRING", "")), keep_blank_values=True)
            selected_view = query.get("view", ["overview"])[0]
            selected_instrument = query.get("instrument", ["TMF"])[0]
            detail = query.get("detail", [""])[0] == "1"
            body = render_account_html(account_source, account_thresholds, margin_source, selected_view=selected_view, selected_instrument=selected_instrument, detail=detail).encode()
            start_response("200 OK", [("Content-Type", "text/html; charset=utf-8"), ("Content-Length", str(len(body)))])
            return [body]
        if path != "/":
            start_response("404 Not Found", [("Content-Type", "text/plain; charset=utf-8")]); return ["找不到頁面。".encode()]
        query = parse_qs(str(environ.get("QUERY_STRING", "")), keep_blank_values=True)
        snapshot = market_data_source.read_snapshot(query.get("instrument", [DEFAULT_MARKET_PRODUCT])[0])
        body = render_operator_html(view_provider(), snapshot)
        runtime_mode = getattr(market_data_source, "mode", None)
        runtime_status = getattr(market_data_source, "status", None)
        if str(runtime_mode) == "fake-live":
            label = "模擬即時行情｜WebSocket 模擬連線｜連線就緒" if str(runtime_status) == "READY" else "模擬即時行情｜連線降級｜資料不足／無法判讀"
            body = body.replace("離線示範行情｜", label + "｜", 1)
        elif str(runtime_mode) == "fugle-live":
            body = body.replace("離線示範行情｜", "真實行情來源尚未啟用｜資料不足／無法判讀｜", 1)
        body = body.encode(); start_response("200 OK", [("Content-Type", "text/html; charset=utf-8"), ("Content-Length", str(len(body)))]); return [body]
    return app
