"""GET-only local WSGI dashboard renderer."""
from __future__ import annotations

import json
from dataclasses import replace
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from html import escape
from math import isfinite
from pathlib import Path
from typing import Callable, Iterable, Mapping
from urllib.parse import parse_qs
from zoneinfo import ZoneInfo

from kam_market_ai.live_read_only.market_snapshot import (
    DEFAULT_MARKET_PRODUCT,
    OFFLINE_DEMO_MARKET_DATA_SOURCE,
    MarketDataReadOnlySource,
    MarketDataSource,
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
    demo = view.demo or {}
    try:
        bull = int(round(float(demo.get("bull_score", 50)) / 10))
    except (TypeError, ValueError):
        bull = 5
    bull = max(0, min(10, bull))
    if "unconfirmed_score" not in demo:
        classes = ("bull",) * bull + ("bear",) * (10 - bull)
    else:
        try:
            bear = int(round(float(demo.get("bear_score", 0)) / 10))
        except (TypeError, ValueError):
            bear = 0
        bear = max(0, min(10 - bull, bear))
        classes = ("bull",) * bull + ("unconfirmed",) * (10 - bull - bear) + ("bear",) * bear
    return bull, "".join(f"<span class='control-cell {name}' aria-hidden='true'></span>" for name in classes)

def _control_label(view: PaperTradingOperatorView, bull: int) -> str:
    demo = view.demo or {}
    if "unconfirmed_score" not in demo:
        return f"多方 {bull}｜空方 {10-bull}"
    try:
        bear = int(round(float(demo.get("bear_score", 0)) / 10))
    except (TypeError, ValueError):
        bear = 0
    bear = max(0, min(10 - bull, bear))
    return f"多方 {bull}｜空方 {bear}\n未確認 {10-bull-bear}"


def _numeric_price(value: object) -> float | None:
    try:
        number = float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return None
    return number if isfinite(number) else None


def _display_price(value: object) -> str:
    number = _numeric_price(value)
    if number is None:
        return "尚未形成"
    rounded = Decimal(str(number)).quantize(Decimal(1), rounding=ROUND_HALF_UP)
    return f"{int(rounded):,}"


def _reference_level_text(
    candidates: list[tuple[float, str]],
    *,
    current: float | None,
    resistance: bool,
) -> str:
    if not candidates:
        return "尚未形成"
    if current is None:
        level, source = (min if resistance else max)(candidates)
        return f"{_display_price(level)}（{source.replace(' ', '')}）"
    preferred = [item for item in candidates if item[0] >= current]
    if not resistance:
        preferred = [item for item in candidates if item[0] <= current]
    if preferred:
        level, source = (min if resistance else max)(preferred)
        distance = abs(level - current)
        sign = "+" if resistance else "−"
        relation = f"{sign}{_display_price(distance)}點"
    else:
        level, source = (max if resistance else min)(candidates)
        distance = abs(level - current)
        relation = f"已突破 {_display_price(distance)}點" if resistance else f"已跌破 {_display_price(distance)}點"
    return f"{_display_price(level)}（{source.replace(' ', '')}／{relation}）"


def _cycle_market_references(demo: Mapping[str, object]) -> str:
    details = demo.get("timeframe_details")
    details = details if isinstance(details, Mapping) else {}
    current = _numeric_price(demo.get("current_price"))
    sixty = details.get("60 分")
    sixty = sixty if isinstance(sixty, Mapping) else {}
    ma20 = _display_price(sixty.get("ma20"))
    ma_relation = {"above": "現價在上", "below": "現價在下", "equal": "現價貼近"}.get(
        str(sixty.get("price_vs_ma20", "")),
        "",
    )
    ma_direction = {"rising": "上彎", "falling": "下彎", "flat": "走平"}.get(
        str(sixty.get("ma20_direction", "")),
        "",
    )
    if ma20 != "尚未形成" and (ma_relation or ma_direction):
        ma20 += f"（{'・'.join(item for item in (ma_relation, ma_direction) if item)}）"
    resistance_levels: list[tuple[float, str]] = []
    support_levels: list[tuple[float, str]] = []
    for label in ("15 分", "60 分", "日線", "週線"):
        frame = details.get(label)
        if not isinstance(frame, Mapping):
            continue
        resistance_value = _numeric_price(frame.get("range_resistance"))
        support_value = _numeric_price(frame.get("range_support"))
        if resistance_value is not None:
            resistance_levels.append((resistance_value, label))
        if support_value is not None:
            support_levels.append((support_value, label))
    rows = (
        ("cycle-market-current", "即時微台", _display_price(current)),
        ("cycle-market-ma", "60分20MA", ma20),
        (
            "cycle-market-resistance",
            "最近上壓",
            _reference_level_text(resistance_levels, current=current, resistance=True),
        ),
        (
            "cycle-market-support",
            "最近下撐",
            _reference_level_text(support_levels, current=current, resistance=False),
        ),
    )
    return "".join(
        f"<div class='cycle-market-reference {class_name}'><dt>{label}</dt><dd>{escape(value)}</dd></div>"
        for class_name, label, value in rows
    )

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
    previous = "資料恢復後判讀" if index == 0 else _STAGES[index - 1][0]
    following = "資料恢復後判讀" if index == 0 else _STAGES[min(8, index + 1)][0]
    next_step = str(demo.get("next_step", "等待資料完整"))
    risk = "不可判讀" if index == 0 else "偏高" if index >= 5 else "風險受控"
    market_references = _cycle_market_references(demo)
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
          {market_references}
          <div><dt>目前位置</dt><dd>{escape(stage)}</dd></div>
          <div><dt>循環狀態</dt><dd>{escape(state)}</dd></div>
          <div><dt>上一階段</dt><dd>{escape(previous)}</dd></div>
          <div><dt>下一階段</dt><dd>{escape(following)}</dd></div>
          <div><dt>唯一下一步</dt><dd>{escape(next_step)}</dd></div>
          <div><dt>風險</dt><dd>{risk}</dd></div>
        </dl>
      </div>
      <p class='cycle-note'>倒 U 為市場位置判讀；壓力／支撐為 20 棒區間參考，不是買賣訊號。</p>
    </section>"""

def _rows(values: dict[str, str]) -> str:
    return "".join(f"<dt>{escape(key.replace('_', ' '))}</dt><dd title='{escape(str(value))}'>{escape(str(value)[:10]) if key.endswith('hash') else escape(str(value))}</dd>" for key, value in values.items())


def _timeframe_card(name: object, state: object, details: Mapping[str, object] | None = None) -> str:
    """Apply a compact, presentation-only vocabulary to existing timeframe values."""
    raw = str(state)
    code, interpretation = {
        "AU": ("AU", "偏多・已確認"),
        "AF": ("AF", "偏多・形成中"),
        "AD": ("AD", "偏多・資料失效"),
        "NU": ("NU", "中性・已確認"),
        "NF": ("NF", "中性・形成中"),
        "ND": ("ND", "中性・資料失效"),
        "BU": ("BU", "偏空・已確認"),
        "BF": ("BF", "偏空・形成中"),
        "BD": ("BD", "偏空・資料失效"),
        "偏多": ("AU", "多方健康"),
        "整理": ("NF", "整理"),
        "等待確認": ("NF", "等待確認"),
        "觀望": ("NU", "觀望"),
        "偏空": ("BD", "空方健康"),
    }.get(raw, ("—", raw))
    details = details or {}
    frame_status = str(details.get("status", ""))
    if code.endswith("D"):
        condition = {
            "ambiguous": "結構待確認",
            "unavailable": "資料不足",
            "insufficient": "資料不足",
            "invalid": "資料異常",
            "stale": "資料失效",
        }.get(frame_status)
        bias = {"A": "偏多", "N": "中性", "B": "偏空"}.get(code[:1])
        if frame_status == "ambiguous":
            observed = {
                str(details.get("position", "")),
                str(details.get("trend", "")),
            }
            if observed == {"bullish"}:
                bias = "偏多觀察"
            elif observed == {"bearish"}:
                bias = "偏空觀察"
            elif "bullish" in observed and "bearish" not in observed:
                bias = "偏多傾向"
            elif "bearish" in observed and "bullish" not in observed:
                bias = "偏空傾向"
            elif "bullish" in observed and "bearish" in observed:
                bias = "方向分歧"
        if condition is not None and bias is not None:
            interpretation = f"{bias}・{condition}"
    ma20 = details.get("ma20")
    relation = {"above": "上方", "below": "下方", "equal": "貼近", "insufficient": "尚未形成"}.get(str(details.get("price_vs_ma20", "insufficient")), "資料不足")
    direction = {"rising": "上彎", "falling": "下彎", "flat": "走平", "insufficient": "尚未形成"}.get(str(details.get("ma20_direction", "insufficient")), "資料不足")
    try:
        ma_text = f"（20MA {_display_price(ma20)}）" if ma20 is not None else ""
    except (TypeError, ValueError):
        ma_text = ""
    resistance = _display_price(details.get("range_resistance"))
    support = _display_price(details.get("range_support"))
    try:
        range_bars = max(0, int(details.get("range_window_bars", 0)))
    except (TypeError, ValueError):
        range_bars = 0
    range_label = f"{range_bars}棒" if range_bars else "區間"
    status_code = "" if code == "ND" else f"<strong>{escape(code)}</strong>"
    return (
        "<article class='timeframe-card'>"
        f"<b>{escape(str(name))}</b>{status_code}<span>{escape(interpretation)}</span>"
        f"<small>價格相對 20MA：{escape(relation + ma_text)}</small><small>20MA 方向：{escape(direction)}</small>"
        f"<small class='timeframe-resistance'>{range_label}壓力：{escape(resistance)}</small>"
        f"<small class='timeframe-support'>{range_label}支撐：{escape(support)}</small></article>"
    )


def _frontend_timeframe_cards(timeframes: Iterable[tuple[object, object]], details: object = None) -> str:
    """Keep 5-minute data available to rules while omitting its dashboard card."""
    by_label = details if isinstance(details, Mapping) else {}
    return "".join(
        _timeframe_card(name, state, by_label.get(str(name)) if isinstance(by_label.get(str(name)), Mapping) else None)
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
    disclaimer_lines = (
        "風險聲明：本系統僅供研究、模擬與決策輔助，不構成投資建議、獲利保證或代客操作。模擬績效不代表未來結果；行情與系統資料可能延遲、錯誤或中斷。",
        "期貨具高槓桿，可能產生超過原始保證金之損失；所有實際委託均由使用者自行判斷並於券商端操作，交易結果與損益由使用者自行承擔。",
    )
    disclaimer = "".join(f"<span>{escape(line)}</span>" for line in disclaimer_lines)
    return f"""<!doctype html><html lang='zh-Hant-TW'><head><meta charset='utf-8'><title>{escape(view.title)}</title><link rel='stylesheet' href='/static/operator.css'></head><body><main><header><h1>{escape(view.title)}</h1><a class='account-chip' href='/account'>期貨帳戶｜資金安全</a><span>{escape(str(demo.get('instrument', '—')))}</span><span>資料狀態：{'DEMO' if demo else '本機'}</span><span>PAPER TRADING</span><span>唯讀模式・模擬執行・禁止真實下單</span></header><div class='banner'>{escape(str(demo.get('banner', '尚未載入模擬委託建議。本機頁面目前為唯讀模式。')))}</div><div class='dashboard'><section class='direction-card'><h2>市場方向</h2><strong>{escape(str(demo.get('direction', '—')))}</strong><p>{escape(str(demo.get('direction_reason', '尚未載入方向資料')))}</p></section><section class='control-card'><h2>多空控制權</h2><strong>多方 {bull}｜空方 {10-bull}</strong><small>控制權分裂</small><div class='control-cells'>{cells}</div></section>{_cycle(view)}<section class='timeframes'><h2>四週期狀態</h2><div>{frames}</div></section><section><h2>趨勢健康度</h2><strong>{escape(str(demo.get('trend_health', '—')))}</strong></section><section><h2>目前模擬部位</h2><strong>{escape(str(demo.get('position', '無部位')))}</strong><p>現價 {escape(str(demo.get('current_price', '—')))} · 未實現 {escape(str(demo.get('unrealized_pnl', '—')))}</p></section><section class='next-card next-wait'><h2>唯一下一步</h2><strong>{escape(str(demo.get('next_step', '等待資料完整')))}</strong></section><section class='proposal'><h2>模擬委託建議</h2><dl>{_rows(view.proposal)}</dl></section><section class='matching'><h2>模擬撮合結果</h2><dl>{_rows(view.matching)}</dl></section></div><footer><div class='footer-metrics'><span>模擬現金：{escape(str(view.ledger.get('cash', '—')))}</span><span>模擬部位：{escape(str(view.ledger.get('positions', '—')))}</span><span>已實現損益：—</span><span>未實現損益：{escape(str(demo.get('unrealized_pnl', '—')))}</span><span>緊急停止：{'已啟動' if view.emergency_stop else '未啟動'}</span><span class='audit'>稽核紀錄：{audit}</span></div><p class='risk-disclaimer'>{disclaimer}</p></footer></main></body></html>"""


_ACCOUNT_TABS = (("overview", "帳戶總覽"), ("water-level", "資金水位"), ("position", "商品部位"), ("settings", "設定"))
_ACCOUNT_DISPLAY_TEXT = {
    "UNKNOWN": "資料不足／無法判讀",
    "SAFE": "安全",
    "CAUTION": "注意",
    "DANGER": "危險",
    "DEMO": "示範資料",
    "offline-demo-account-snapshot": "離線示範帳戶快照",
    "offline-demo-margin-snapshot": "離線示範保證金快照",
    "taifex-index-margin-2026-08-12": "期交所 2026-08-12 股價指數類保證金",
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
    frames = _frontend_timeframe_cards(demo.get("timeframes", ()), demo.get("timeframe_details"))
    control_label = _control_label(view, bull)
    audit = "".join(f"<li title='{escape(item['hash'])}'>{escape(item['type'])} · {escape(item['hash'][:10])}</li>" for item in view.audit_events[-3:])
    proposal_title = "自動模擬執行" if demo.get("automation_mode") == "AUTO PAPER" else "模擬委託建議"
    proposal = f"<section class='proposal'><h2>{proposal_title}</h2><dl>{_rows(view.proposal)}</dl></section>"
    if snapshot.status is MarketSnapshotStatus.INVALID_PRODUCT:
        proposal = "<section class='proposal'><h2>模擬委託建議</h2><p>商品代碼無效，未載入模擬委託建議。</p></section>"
    disclaimer_lines = (
        "風險聲明：本系統僅供研究、模擬與決策輔助，不構成投資建議、獲利保證或代客操作。模擬績效不代表未來結果；行情與系統資料可能延遲、錯誤或中斷。",
        "期貨具高槓桿，可能產生超過原始保證金之損失；所有實際委託均由使用者自行判斷並於券商端操作，交易結果與損益由使用者自行承擔。",
    )
    disclaimer = "".join(f"<span>{escape(line)}</span>" for line in disclaimer_lines)
    return f"""<!doctype html><html lang='zh-Hant-TW'><head><meta charset='utf-8'><title>{escape(view.title)}</title><link rel='stylesheet' href='/static/operator.css'></head><body><main><header><h1>{escape(view.title)}</h1>{_market_header_status(snapshot)}<a class='account-chip' href='/account'>期貨帳戶｜資金安全</a>{_market_snapshot_header(snapshot)}</header><div class='banner'>{escape(str(demo.get('banner', '尚未載入模擬委託建議。本機頁面目前為唯讀模式。')))} · 目前僅 Header 已切換至離線示範行情；決策卡尚未接入此商品 snapshot。</div><div class='dashboard'><section class='direction-card'><h2>市場方向</h2><strong>{escape(str(demo.get('direction', '—')))}</strong><p>{escape(str(demo.get('direction_reason', '尚未載入方向資料')))}</p></section><section class='control-card'><h2>多空控制權</h2><strong>{escape(control_label)}</strong><small>控制權分裂</small><div class='control-cells'>{cells}</div></section>{_cycle(view)}<section class='timeframes'><h2>四週期狀態</h2><div>{frames}</div></section><section class='trend-health-card'><h2>趨勢健康度</h2><strong>{escape(str(demo.get('trend_health', '—')))}</strong></section><section class='position-card'><h2>目前模擬部位</h2><strong>{escape(str(demo.get('position', '無部位')))}</strong><p>現價 {escape(str(demo.get('current_price', '—')))} · 未實現 {escape(str(demo.get('unrealized_pnl', '—')))}</p></section><section class='next-card next-wait'><h2>唯一下一步</h2><strong>{escape(str(demo.get('next_step', '等待資料完整')))}</strong></section>{proposal}<section class='matching'><h2>模擬撮合結果</h2><dl>{_rows(view.matching)}</dl></section></div><footer><div class='footer-metrics'><span>模擬現金：{escape(str(view.ledger.get('cash', '—')))}</span><span>模擬部位：{escape(str(view.ledger.get('positions', '—')))}</span><span>已實現損益：—</span><span>未實現損益：{escape(str(demo.get('unrealized_pnl', '—')))}</span><span>緊急停止：{'已啟動' if view.emergency_stop else '未啟動'}</span><span class='audit'>稽核紀錄：{audit}</span></div><p class='risk-disclaimer'>{disclaimer}</p></footer></main></body></html>"""


_render_terminal_html = render_operator_html


def _market_header_status(snapshot: MarketSnapshot) -> str:
    if snapshot.status is MarketSnapshotStatus.INVALID_PRODUCT:
        return "<span class='header-market-status'>商品代碼無效｜帳戶未連線・券商未連線・唯讀模式・禁止真實下單</span>"
    session = {"DAY": "日盤", "NIGHT": "夜盤", "CLOSED": "休市", "UNKNOWN": "資料不足／無法判讀"}[snapshot.trading_session.value]
    freshness = {"FRESH": "資料新鮮", "STALE": "資料延遲", "EXPIRED": "資料過期", "UNKNOWN": "資料不足／無法判讀"}[snapshot.freshness.value]
    timestamp = snapshot.timestamp
    display_time = "—"
    if isinstance(timestamp, datetime) and timestamp.tzinfo is not None:
        display_time = timestamp.astimezone(ZoneInfo("Asia/Taipei")).strftime("%Y-%m-%d %H:%M")
    return f"<span class='header-market-status'>資料時間（台灣）：{display_time}｜{session}｜{freshness}｜帳戶未連線・券商未連線・唯讀模式・禁止真實下單</span>"


def _market_status_line(snapshot: MarketSnapshot) -> str:
    if snapshot.status is MarketSnapshotStatus.INVALID_PRODUCT:
        return "商品代碼無效"
    return f"{snapshot.instrument_name}・{snapshot.product_code}｜{snapshot.contract_code}・{snapshot.contract_month}｜最新 {_money(snapshot.last_price)}・量 {_money(snapshot.volume)}"


def _account_drawer_html() -> str:
    return """<div class='account-drawer-backdrop' data-account-drawer-close hidden></div><aside id='account-drawer' class='account-drawer' role='dialog' aria-modal='true' aria-labelledby='account-drawer-title' aria-hidden='true'><header class='account-drawer-header'><div><h2 id='account-drawer-title'>期貨帳戶｜資金安全</h2><p>示範帳戶・唯讀模式・禁止真實交易</p></div><button type='button' class='account-drawer-close' data-account-drawer-close aria-label='關閉帳戶抽屜'>關閉</button></header><nav class='account-drawer-tabs' aria-label='帳戶檢視'><a href='/account?view=overview' target='account-drawer-frame'>帳戶總覽</a><a href='/account?view=water-level' target='account-drawer-frame'>資金水位</a><a href='/account?view=position&amp;instrument=TMF' target='account-drawer-frame'>商品部位</a><a href='/account?view=settings' target='account-drawer-frame'>設定</a></nav><iframe class='account-drawer-frame' name='account-drawer-frame' title='KAM 帳戶中心唯讀內容' src='/account?view=overview'></iframe><footer class='account-drawer-footer'><span>帳戶未連線</span><span>券商未連線</span><span>交易功能停用</span><span>禁止真實下單</span><span>緊急停止未啟動</span><a href='/account'>開啟完整帳戶中心</a></footer></aside><script>(function(){const trigger=document.getElementById('account-drawer-trigger'),drawer=document.getElementById('account-drawer'),backdrop=document.querySelector('.account-drawer-backdrop'),close=()=>{drawer.classList.remove('is-open');drawer.setAttribute('aria-hidden','true');backdrop.hidden=true;trigger.setAttribute('aria-expanded','false');trigger.focus()},open=()=>{drawer.classList.add('is-open');drawer.setAttribute('aria-hidden','false');backdrop.hidden=false;trigger.setAttribute('aria-expanded','true');drawer.querySelector('.account-drawer-close').focus()};trigger.addEventListener('click',()=>drawer.classList.contains('is-open')?close():open());document.querySelectorAll('[data-account-drawer-close]').forEach(item=>item.addEventListener('click',close));document.addEventListener('keydown',event=>{if(event.key==='Escape'&&drawer.classList.contains('is-open'))close()})})();</script>"""


def render_help_html() -> str:
    """Render the static, GET-only operating guide without trading capability."""
    return """<!doctype html><html class='help-page' lang='zh-Hant-TW'><head><meta charset='utf-8'><title>KAM 使用說明｜SOP</title><link rel='stylesheet' href='/static/operator.css'></head><body class='help-page'><main class='help-main'>
      <header><div><h1>KAM 使用說明｜SOP</h1><small>先判斷、再等待；只有條件完整才行動</small></div><nav class='help-nav' aria-label='主要頁面'><a class='account-chip' href='/'>市場儀表板</a><a class='account-chip' href='/account'>期貨帳戶｜資金安全</a></nav><span>研究與模擬用途・禁止真實自動下單</span></header>
      <div class='help-banner'>KAM 是交易決策作業系統，不是承諾獲利的交易指示工具。它只清楚回答兩件事：當前是否具備交易條件，以及下一步應採取什麼行動。</div>
      <nav class='help-toc' aria-label='本頁目錄'><a href='#daily-sop'>每日 SOP</a><a href='#read-order'>判讀順序</a><a href='#horizons'>週期與持有時間</a><a href='#rollover'>每月換倉</a><a href='#paper'>模擬紀錄</a><a href='#stop'>停止條件</a></nav>
      <div class='help-content'>
        <section id='daily-sop' class='help-section'><h2>一、每日使用 SOP</h2><ol class='help-steps'>
          <li><strong>先確認資料。</strong><span>商品代碼、契約月份、台灣資料時間、日盤／夜盤及 WebSocket 狀態都正確；資料過期、中斷或契約不明時停止判讀。</span></li>
          <li><strong>先看長週期。</strong><span>週線決定大方向，日線確認目前是延伸、回檔或整理；長週期不清楚時，不用短週期猜方向。</span></li>
          <li><strong>再看核心週期。</strong><span>60 分確認結構與位置，15 分負責進場確認；5 分只作觸發，不得單獨推翻大週期。</span></li>
          <li><strong>檢查品質閘門。</strong><span>確認市場型態、週期一致、位置、報酬風險、波動、資料品質及當日風控。任何硬性否決出現，就不建立模擬委託。</span></li>
          <li><strong>只讀唯一下一步。</strong><span>依畫面執行「等待、模擬進場、續抱、減碼或禁止交易」其中一項；不要自行拼接多個訊號。</span></li>
          <li><strong>先模擬、後檢討。</strong><span>保存進出場、停損、成本、滑價、否決原因與結果。持倉途中不臨時改規則，修正版從下一批樣本才生效。</span></li>
        </ol></section>
        <section id='read-order' class='help-section'><h2>二、畫面判讀順序</h2><div class='help-grid'>
          <article><b>1｜市場方向</b><p>先判斷偏多、偏空或不可判讀。</p></article><article><b>2｜多空控制權</b><p>檢查力量是否一致，避免在分裂狀態追價。</p></article><article><b>3｜市場循環位置</b><p>確認處於築底、起漲、延伸、過熱或轉弱；位置不是價格預測。</p></article><article><b>4｜四週期狀態</b><p>週、日、60 分、15 分是否同向；5 分保留在後台作觸發。</p></article><article><b>5｜趨勢健康度</b><p>辨認健康延伸、衰退或資料不足。</p></article><article><b>6｜唯一下一步</b><p>最後才決定模擬行動；前面任一關不完整即等待。</p></article>
        </div></section>
        <section id='horizons' class='help-section'><h2>三、週期與預期持有時間</h2><div class='help-table-wrap'><table class='help-table'><thead><tr><th>操作層級</th><th>主要判讀週期</th><th>概念持有時間</th><th>KAM 用法</th></tr></thead><tbody>
          <tr><td>長週期</td><td>月線／週線</td><td>約數週至一個月以上</td><td>決定主要方向與大位置，不用來精準抓進場點。</td></tr><tr><td>中期波段</td><td>日線／60 分</td><td>約數天至數週</td><td>日線定狀態，60 分是進出場與結構判讀核心。</td></tr><tr><td>短波段</td><td>60 分／15 分</td><td>約數小時至數天</td><td>60 分找結構，15 分確認，必須服從長週期風險。</td></tr><tr><td>當沖</td><td>15 分／5 分</td><td>同一交易日</td><td>5 分只作觸發；不得因短線轉強就忽略週、日方向與重要位置。</td></tr>
        </tbody></table></div><p class='help-note'>持有時間是操作分類，不是到期承諾。停損、結構破壞、資料異常或風控停止條件出現時，應優先處理風險；期貨月契約也不適合把「長週期」理解成無限期持有同一契約。</p></section>
        <section id='rollover' class='help-section'><h2>四、臺指類期貨每月結算與換倉</h2><div class='rollover-alert'><strong>法定規則</strong><p>微型臺指期貨等臺指類月契約，最後交易日為交割月份的第三個星期三；最後交易日一般交易時段至 13:30，該到期月份契約沒有盤後交易。新交割月份契約於最後交易日的下一營業日一般交易時段起掛牌。</p></div><h3>KAM 建議換月流程</h3><ol class='help-steps compact'>
          <li><strong>到期前 5 個營業日開始提醒。</strong><span>這是風險管理觀察窗，不是交易所強制換倉日。</span></li><li><strong>同時比較近月與次月。</strong><span>檢查成交量、未平倉量、買賣價差與報價連續性；流動性尚未轉移前，不因日期機械換月。</span></li><li><strong>建立新部位前先選流動性較佳契約。</strong><span>若次月已成主力，新的模擬訊號改用次月；舊近月部位則分開管理，不可把兩個月份當成同一價格序列。</span></li><li><strong>最晚在最後交易日前完成決策。</strong><span>不熟悉現金結算者，不把未平倉部位留到最後結算；最後交易日也不得期待夜盤再處理。</span></li><li><strong>換月後重新建立基準。</strong><span>記錄價差、切換時間與新契約代碼，重新確認 20MA、原始整理區及四週期資料連續性，禁止直接沿用錯誤價位。</span></li>
        </ol><p class='help-note'>交易所規定的是最後交易日與結算方式；「哪一天換倉」屬操作決策。實際日期遇休市或制度調整時，以臺灣期貨交易所當年度行事曆、契約規格及券商通知為準。</p></section>
        <section id='paper' class='help-section'><h2>五、模擬測試與版本調整</h2><ul class='help-list'><li>A 級條件通過才列入主要樣本；等待與禁止也保留原因。</li><li>每筆計入手續費、交易稅與模擬滑價，分開記錄日盤、夜盤與契約月份。</li><li>至少 30 筆已完成 A 級樣本後，才檢查勝率、平均盈虧、成本後期望值與最大回撤。</li><li>發現程式錯誤可立即修復；策略門檻則鎖定到本批結束，避免邊測邊調造成結果失真。</li><li>每個版本獨立統計，只有樣本外結果改善，才考慮保留新規則。</li></ul></section>
        <section id='stop' class='help-section'><h2>六、立即停止的情況</h2><div class='stop-grid'><span>資料時間過期或中斷</span><span>契約月份不明或已進入結算風險</span><span>四週期資料缺漏或嚴重衝突</span><span>價差、波動或成交異常</span><span>連續虧損 2 次</span><span>單日虧損達 40 點</span><span>單日交易達 5 次</span><span>模擬持倉或帳戶狀態不同步</span></div></section>
        <section class='help-section help-risk'><h2>風險聲明</h2><p>本系統僅供研究、模擬與決策輔助，不構成投資建議、獲利保證或代客操作。模擬績效不代表未來結果；行情與系統資料可能延遲、錯誤或中斷。期貨具高槓桿，可能產生超過原始保證金之損失；所有實際委託均由使用者自行判斷並於券商端操作，交易結果與損益由使用者自行承擔。</p></section>
      </div>
    </main></body></html>"""


def render_operator_html(view: PaperTradingOperatorView, snapshot: MarketSnapshot | None = None) -> str:
    """Add a client-only Account Drawer around the existing read-only terminal."""
    snapshot = snapshot or OFFLINE_DEMO_MARKET_DATA_SOURCE.read_snapshot(DEFAULT_MARKET_PRODUCT)
    presentation = SelectedSnapshotDecisionPresenter().present(snapshot, view.demo)
    demo = dict(view.demo or {})
    preserve_five_timeframe = demo.get("source_kind") == "FUBON_LIVE_FIVE_TIMEFRAME"
    bull_cells = presentation.control.bull_score
    if not preserve_five_timeframe:
        demo.update({"direction": presentation.direction.label, "direction_reason": presentation.direction.reason, "bull_score": bull_cells * 10 if bull_cells is not None else 50, "cycle_label": presentation.cycle.label, "trend_health": presentation.trend_health.label, "next_step": presentation.next_step.label, "timeframes": tuple((item.timeframe, item.label) for item in presentation.timeframes), "u_stage": "U0" if presentation.cycle.state in {"closed", "halted", "invalid", "live-data-only"} else "U3"})
    rendered_view = view
    if snapshot.data_source is MarketDataSource.FUTURE_LIVE:
        demo.update(
            {
                "current_price": _money(snapshot.last_price),
                "unrealized_pnl": "—",
            }
        )
        if not preserve_five_timeframe:
            demo["position"] = "尚未接入"
            rendered_view = replace(
                view,
                proposal={"status": "尚未接入真實行情決策"},
                matching={"state": "尚未接入"},
            )
    html = _render_terminal_html(replace(rendered_view, demo=demo), snapshot)
    if preserve_five_timeframe:
        html = html.replace(
            " · 目前僅 Header 已切換至離線示範行情；決策卡尚未接入此商品 snapshot。",
            f" · 商品 {escape(str(demo.get('instrument', 'TMF')))}",
            1,
        )
    if bull_cells is None and not preserve_five_timeframe:
        html = html.replace("多方 5｜空方 5", "不可判讀", 1)
        html = html.replace("<small>控制權分裂</small>", "<small>等待四週期資料</small>", 1)
        html = html.replace(
            "<div class='control-cells'>",
            "<div class='control-cells control-cells-unscored' "
            "aria-label='多空顏色圖例；等待四週期資料後顯示分數'>",
            1,
        )
    html = html.replace(
        "<section><h2>趨勢健康度</h2>",
        "<section class='trend-health-card'><h2>趨勢健康度</h2>",
        1,
    )
    html = html.replace(
        "<section><h2>目前模擬部位</h2>",
        "<section class='position-card'><h2>目前模擬部位</h2>",
        1,
    )
    trigger = "<button id='account-drawer-trigger' class='account-chip account-drawer-trigger' type='button' aria-expanded='false' aria-controls='account-drawer'>期貨帳戶｜資金安全</button>"
    html = html.replace("<a class='account-chip' href='/account'>期貨帳戶｜資金安全</a>", trigger, 1)
    html = html.replace(trigger, trigger + "<a class='account-chip' href='/charts'>多週期 K 線</a><a class='account-chip' href='/help'>使用說明｜SOP</a>", 1)
    html = html.replace("<span class='header-readonly-note'>帳戶未連線・券商未連線・唯讀模式・模擬執行・禁止真實下單</span>", "", 1)
    if not preserve_five_timeframe:
        banner_start = html.index("<div class='banner'>")
        banner_end = html.index("</div>", banner_start) + len("</div>")
        html = html[:banner_start] + f"<div class='banner market-status-line' title='OFFLINE_DEMO'>離線示範行情｜{_market_status_line(snapshot)}</div>" + html[banner_end:]
    html = html.replace("<h2>模擬委託建議</h2>", "<h2>模擬委託建議</h2><p>決策呈現已切換；模擬委託流程尚未接入此商品 snapshot。</p>", 1)
    html = html.replace("<h2>模擬撮合結果</h2>", "<h2>模擬撮合結果</h2><p>決策呈現已切換；模擬委託流程尚未接入此商品 snapshot。</p>", 1)
    return html.replace("</main></body>", _account_drawer_html() + "</main></body>", 1)


def _runtime_source_status(source: object) -> object:
    getter = getattr(source, "runtime_status", None)
    return getter() if callable(getter) else getattr(source, "status", "READY")


def build_operator_wsgi(view_provider: Callable[[], PaperTradingOperatorView], account_source: AccountReadOnlySource = DEMO_ACCOUNT_SOURCE, account_thresholds: CapitalSafetyThresholds = DEMO_ACCOUNT_THRESHOLDS, margin_source: MarginRequirementSource = DEMO_MARGIN_SOURCE, market_data_source: MarketDataReadOnlySource = OFFLINE_DEMO_MARKET_DATA_SOURCE, public_embed_config=None, chart_data_source=None) -> Callable[..., Iterable[bytes]]:
    from kam_market_ai.live_read_only.decision_presentation import SelectedSnapshotDecisionPresenter
    from kam_market_ai.paper_trading.embed_presenter import EmbedPagePresenter
    from kam_market_ai.paper_trading.public_routes import build_health_response
    from kam_market_ai.paper_trading.multi_timeframe_chart import EMPTY_CHART_DATA_SOURCE, render_multi_timeframe_chart_html
    from kam_market_ai.public_deployment import PublicEmbedConfig
    public_embed_config = public_embed_config or PublicEmbedConfig()
    chart_data_source = chart_data_source or EMPTY_CHART_DATA_SOURCE
    css_path = Path(__file__).with_name("static") / "operator.css"
    chart_refresh_path = Path(__file__).with_name("static") / "chart-refresh.js"
    dashboard_refresh_path = Path(__file__).with_name("static") / "dashboard-refresh.js"
    def app(environ: dict[str, object], start_response: Callable[..., object]) -> Iterable[bytes]:
        path, method = str(environ.get("PATH_INFO", "/")), str(environ.get("REQUEST_METHOD", "GET"))
        headers = [("Content-Security-Policy", public_embed_config.content_security_policy), ("X-Content-Type-Options", "nosniff"), ("Referrer-Policy", "strict-origin-when-cross-origin"), ("Permissions-Policy", "geolocation=(), camera=(), microphone=()"), ("Cache-Control", "no-store")]
        if path == "/healthz" and method == "GET":
            response = build_health_response(); body = response.body.encode()
            start_response("200 OK", [("Content-Type", response.content_type), *headers]); return [body]
        if path == "/readyz" and method == "GET":
            source_mode = str(getattr(market_data_source, "mode", "offline-demo"))
            ready = str(_runtime_source_status(market_data_source)) == "READY" and source_mode != "fugle-live"
            payload = {
                "status": "ready" if ready else "not_ready",
                "source_mode": source_mode,
                "trading_enabled": False,
            }
            body = json.dumps(payload, separators=(",", ":")).encode()
            start_response("200 OK" if ready else "503 Service Unavailable", [("Content-Type", "application/json; charset=utf-8"), *headers]); return [body]
        if method != "GET":
            start_response("405 Method Not Allowed", [("Content-Type", "text/plain; charset=utf-8"), ("Allow", "GET")]); return ["唯讀端點，不接受此操作。".encode()]
        if path == "/static/operator.css":
            start_response("200 OK", [("Content-Type", "text/css; charset=utf-8")]); return [css_path.read_bytes()]
        if path == "/static/chart-refresh.js":
            start_response("200 OK", [("Content-Type", "text/javascript; charset=utf-8"), *headers]); return [chart_refresh_path.read_bytes()]
        if path == "/static/dashboard-refresh.js":
            start_response("200 OK", [("Content-Type", "text/javascript; charset=utf-8"), *headers]); return [dashboard_refresh_path.read_bytes()]
        if path == "/embed":
            if not public_embed_config.enable_embed:
                start_response("404 Not Found", [("Content-Type", "text/plain; charset=utf-8"), *headers]); return [b"Not found"]
            query = parse_qs(str(environ.get("QUERY_STRING", "")), keep_blank_values=True)
            selected = query.get("instrument", [DEFAULT_MARKET_PRODUCT])[0]
            snapshot = market_data_source.read_snapshot(selected)
            decision = SelectedSnapshotDecisionPresenter().present(snapshot)
            runtime_status = _runtime_source_status(market_data_source)
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
        if path == "/help":
            body = render_help_html().encode()
            start_response("200 OK", [("Content-Type", "text/html; charset=utf-8"), ("Content-Length", str(len(body))), *headers])
            return [body]
        if path == "/charts":
            query = parse_qs(str(environ.get("QUERY_STRING", "")), keep_blank_values=True)
            body = render_multi_timeframe_chart_html(
                chart_data_source,
                instrument=query.get("instrument", [DEFAULT_MARKET_PRODUCT])[0],
                timeframe=query.get("timeframe", ["60m"])[0],
            ).encode()
            start_response("200 OK", [("Content-Type", "text/html; charset=utf-8"), ("Content-Length", str(len(body))), *headers])
            return [body]
        if path != "/":
            start_response("404 Not Found", [("Content-Type", "text/plain; charset=utf-8")]); return ["找不到頁面。".encode()]
        query = parse_qs(str(environ.get("QUERY_STRING", "")), keep_blank_values=True)
        snapshot = market_data_source.read_snapshot(query.get("instrument", [DEFAULT_MARKET_PRODUCT])[0])
        body = render_operator_html(view_provider(), snapshot)
        runtime_mode = getattr(market_data_source, "mode", None)
        runtime_status = _runtime_source_status(market_data_source)
        if str(runtime_mode) == "fake-live":
            label = "模擬即時行情｜WebSocket 模擬連線｜連線就緒" if str(runtime_status) == "READY" else "模擬即時行情｜連線降級｜資料不足／無法判讀"
            body = body.replace("離線示範行情｜", label + "｜", 1)
        elif str(runtime_mode) == "fugle-live":
            body = body.replace("離線示範行情｜", "真實行情來源尚未啟用｜資料不足／無法判讀｜", 1)
        elif str(runtime_mode) == "fubon-live":
            label = (
                "富邦真實期貨行情｜WebSocket 連線就緒｜3 秒更新"
                if str(runtime_status) == "READY"
                else "富邦真實期貨行情｜連線中斷｜資料不足／無法判讀"
            )
            body = body.replace("離線示範行情｜", label + "｜", 1)
            body = body.replace("title='OFFLINE_DEMO'", "title='FUTURE_LIVE'", 1)
            body = body.replace(
                "</head>",
                "<script src='/static/dashboard-refresh.js' defer></script></head>",
                1,
            )
            body = body.replace(
                "</header>",
                "<span id='dashboard-live-status' class='dashboard-live-status' "
                "role='status' aria-live='polite'>每 3 秒更新</span></header>",
                1,
            )
        body = body.encode(); start_response("200 OK", [("Content-Type", "text/html; charset=utf-8"), ("Content-Length", str(len(body)))]); return [body]
    return app
