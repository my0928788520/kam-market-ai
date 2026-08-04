"""GET-only local WSGI dashboard renderer."""
from __future__ import annotations

from html import escape
from pathlib import Path
from typing import Callable, Iterable

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


def render_operator_html(view: PaperTradingOperatorView) -> str:
    demo = view.demo or {}; bull, cells = _cells(view)
    frames = "".join(_timeframe_card(name, state) for name, state in demo.get("timeframes", ()))
    audit = "".join(f"<li title='{escape(item['hash'])}'>{escape(item['type'])} · {escape(item['hash'][:10])}</li>" for item in view.audit_events[-3:])
    return f"""<!doctype html><html lang='zh-Hant-TW'><head><meta charset='utf-8'><title>{escape(view.title)}</title><link rel='stylesheet' href='/static/operator.css'></head><body><main><header><h1>{escape(view.title)}</h1><span>{escape(str(demo.get('instrument', '—')))}</span><span>資料狀態：{'DEMO' if demo else '本機'}</span><span>PAPER TRADING</span><span>唯讀模式・模擬執行・禁止真實下單</span></header><div class='banner'>{escape(str(demo.get('banner', '尚未載入模擬委託建議。本機頁面目前為唯讀模式。')))}</div><div class='dashboard'><section class='direction-card'><h2>市場方向</h2><strong>{escape(str(demo.get('direction', '—')))}</strong><p>{escape(str(demo.get('direction_reason', '尚未載入方向資料')))}</p></section><section class='control-card'><h2>多空控制權</h2><strong>多方 {bull}｜空方 {10-bull}</strong><small>控制權分裂</small><div class='control-cells'>{cells}</div></section>{_cycle(view)}<section class='timeframes'><h2>五週期狀態</h2><div>{frames}</div></section><section><h2>趨勢健康度</h2><strong>{escape(str(demo.get('trend_health', '—')))}</strong></section><section><h2>目前模擬部位</h2><strong>{escape(str(demo.get('position', '無部位')))}</strong><p>現價 {escape(str(demo.get('current_price', '—')))} · 未實現 {escape(str(demo.get('unrealized_pnl', '—')))}</p></section><section class='next-card next-wait'><h2>唯一下一步</h2><strong>{escape(str(demo.get('next_step', '等待資料完整')))}</strong></section><section class='proposal'><h2>模擬委託建議</h2><dl>{_rows(view.proposal)}</dl></section><section class='matching'><h2>模擬撮合結果</h2><dl>{_rows(view.matching)}</dl></section></div><footer><span>模擬現金：{escape(str(view.ledger.get('cash', '—')))}</span><span>模擬部位：{escape(str(view.ledger.get('positions', '—')))}</span><span>已實現損益：—</span><span>未實現損益：{escape(str(demo.get('unrealized_pnl', '—')))}</span><span>緊急停止：{'已啟動' if view.emergency_stop else '未啟動'}</span><span class='audit'>稽核紀錄：{audit}</span></footer></main></body></html>"""

def build_operator_wsgi(view_provider: Callable[[], PaperTradingOperatorView]) -> Callable[..., Iterable[bytes]]:
    css_path = Path(__file__).with_name("static") / "operator.css"
    def app(environ: dict[str, object], start_response: Callable[..., object]) -> Iterable[bytes]:
        path, method = str(environ.get("PATH_INFO", "/")), str(environ.get("REQUEST_METHOD", "GET"))
        if method != "GET":
            start_response("405 Method Not Allowed", [("Content-Type", "text/plain; charset=utf-8"), ("Allow", "GET")]); return ["唯讀端點，不接受此操作。".encode()]
        if path == "/static/operator.css":
            start_response("200 OK", [("Content-Type", "text/css; charset=utf-8")]); return [css_path.read_bytes()]
        if path != "/":
            start_response("404 Not Found", [("Content-Type", "text/plain; charset=utf-8")]); return ["找不到頁面。".encode()]
        body = render_operator_html(view_provider()).encode(); start_response("200 OK", [("Content-Type", "text/html; charset=utf-8"), ("Content-Length", str(len(body)))]); return [body]
    return app
