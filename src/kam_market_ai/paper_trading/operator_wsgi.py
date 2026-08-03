"""Local, GET-only WSGI adapter for Paper Trading operator presentation."""
from __future__ import annotations

from html import escape
from pathlib import Path
from typing import Callable, Iterable

from .operator_presenter import PaperTradingOperatorView

_FIELD_LABELS = {
    "status": "狀態", "reasons": "原因", "instrument": "商品", "action": "動作",
    "quantity": "數量", "reference_price": "參考價格", "limit_price": "限價",
    "stop_loss": "停損價格", "take_profit": "停利價格", "confidence": "信心度",
    "risk": "風險狀態", "expires_at": "到期時間", "proposal_hash": "委託建議雜湊",
    "state": "狀態", "fills": "成交筆數", "cash": "模擬現金", "positions": "模擬部位",
    "realized_pnl": "已實現損益", "unrealized_pnl": "未實現損益", "ledger_hash": "帳本雜湊",
}


def render_operator_html(view: PaperTradingOperatorView) -> str:
    """Render local read-only content; values are already escaped by presenter."""
    def rows(values: dict[str, str]) -> str:
        return "".join(
            f"<dt>{escape(_FIELD_LABELS.get(key, key.replace('_', ' ')))}</dt>"
            f"<dd{' class=\"hash\"' if key.endswith('hash') else ''}{' title=\"' + escape(str(value)) + '\"' if key.endswith('hash') else ''}>"
            f"{escape(str(value)[:10]) if key.endswith('hash') else value}</dd>"
            for key, value in values.items()
        )
    audit = "".join(f"<li title='{escape(item['hash'])}'>{item['type']} · {escape(item['hash'][:10])}</li>" for item in view.audit_events[-3:])
    demo_html = ""
    if view.demo:
        frames = "".join(f"<article class='timeframe-card'><b>{escape(str(name))}</b><strong>{escape(str(state))}</strong><small>相對 20MA：—</small><small>20MA 方向：—</small></article>" for name, state in view.demo["timeframes"])
        stage_names = ("位置不明", "低檔築底", "起漲形成", "多方延伸", "延伸後段", "高檔過熱", "起跌形成", "空方延伸", "低檔止跌")
        points = ((18,98),(48,67),(82,38),(116,19),(150,12),(184,19),(218,38),(252,67),(282,98))
        stage_index = int(str(view.demo["u_stage"])[1])
        marker_x, marker_y = points[stage_index]
        u_labels = "<defs><linearGradient id='cycleGradient' x1='0%' x2='100%'><stop offset='0%' stop-color='#ff8aa0'/><stop offset='24%' stop-color='#ff3d52'/><stop offset='45%' stop-color='#ff8b35'/><stop offset='55%' stop-color='#bdf7a1'/><stop offset='76%' stop-color='#37df80'/><stop offset='100%' stop-color='#20c9b5'/></linearGradient><filter id='curveGlow'><feGaussianBlur stdDeviation='3' result='b'/><feMerge><feMergeNode in='b'/><feMergeNode in='SourceGraphic'/></feMerge></filter><filter id='markerGlow'><feGaussianBlur stdDeviation='4' result='b'/><feMerge><feMergeNode in='b'/><feMergeNode in='SourceGraphic'/></feMerge></filter></defs>" + "".join(f"<text class='u-label' x='{x}' y='120'>U{i}</text><title>U{i}｜{stage_names[i]}</title>" for i, (x, _) in enumerate(points)) + f"<circle class='current-marker' cx='{marker_x}' cy='{marker_y}' r='7' filter='url(#markerGlow)'/><text class='stage-label' x='{marker_x+8}' y='{marker_y-9}'>{stage_names[stage_index]}</text>"
        demo_html = f"""<section class='core-card direction'><h2>市場方向</h2><strong>{escape(str(view.demo['direction']))}</strong><p>{escape(str(view.demo['direction_reason']))}</p></section><section class='core-card control'><h2>多空控制權</h2><div class='score bull' style='width:{view.demo['bull_score']}%'>多方 {view.demo['bull_score']}</div><div class='score bear' style='width:{view.demo['bear_score']}%'>空方 {view.demo['bear_score']}</div></section><section class='core-card ucurve'><h2>倒 U 市場位置</h2><svg viewBox='0 0 300 125' role='img' aria-label='倒 U 市場位置圖'><path d='M18 98 Q150 4 282 98' fill='none' stroke='#7185a3' stroke-width='4'/><circle cx='150' cy='18' r='7' fill='#f5c451'/>{u_labels}</svg><b>倒 U 階段：{escape(str(view.demo['u_stage']))}</b><small>倒 U 為市場位置判讀，不是價格預測</small></section><section class='timeframes'><h2>五週期狀態</h2><div>{frames}</div></section><section class='decision-card'><h2>趨勢健康度</h2><strong>{escape(str(view.demo['trend_health']))}</strong></section><section class='decision-card'><h2>目前模擬部位</h2><strong>{escape(str(view.demo['position']))}</strong><p>數量 1・均價 {escape(str(view.demo['average_price']))}・現價 {escape(str(view.demo['current_price']))}・未實現損益 {escape(str(view.demo['unrealized_pnl']))}</p></section><section class='decision-card next'><h2>唯一下一步</h2><strong>{escape(str(view.demo['next_step']))}</strong></section>"""
    proposal_button = "" if view.proposal.get("action") in {"觀望", "—"} or view.emergency_stop else "<button disabled title='僅展示，不會送出任何真實委託'>人工確認並送入模擬撮合</button>"
    return f"""<!doctype html><html lang='zh-Hant-TW'><head><meta charset='utf-8'><title>{escape(view.title)}</title><link rel='stylesheet' href='/static/operator.css'></head><body><main><header><h1>{escape(view.title)}</h1><span>{escape(str(view.demo.get('instrument', '—') if view.demo else '—'))}</span><span>{escape(str(view.demo.get('snapshot_time', '—') if view.demo else '—'))}</span><span>{escape(str(view.demo.get('data_freshness', '尚無資料') if view.demo else '尚無資料'))}</span><span>模式：{'DEMO' if view.demo else '一般'}</span><span>PAPER TRADING</span><span>唯讀模式・模擬執行・禁止真實下單</span><span>v0.1</span></header><div class='banner'>{escape(str(view.demo['banner'])) if view.demo else '尚未載入模擬委託建議。本機頁面目前為唯讀模式。'}</div><div class='dashboard'>{demo_html}<section class='proposal'><h2>模擬委託建議</h2><dl>{rows(view.proposal)}</dl>{proposal_button}<details><summary>主要理由</summary><p>{view.proposal.get('reasons', '—')}</p></details></section><section class='matching'><h2>模擬撮合結果</h2><dl>{rows(view.matching)}</dl></section></div><footer><span>模擬現金：{view.ledger.get('cash', '—')}</span><span>模擬部位：{view.ledger.get('positions', '—')}</span><span>已實現損益：—</span><span>未實現損益：{view.demo.get('unrealized_pnl', '—') if view.demo else '—'}</span><span>緊急停止：{'已啟動' if view.emergency_stop else '未啟動'}</span><span class='audit'>稽核紀錄：{audit}</span></footer></main></body></html>"""


def build_operator_wsgi(view_provider: Callable[[], PaperTradingOperatorView]) -> Callable[..., Iterable[bytes]]:
    css_path = Path(__file__).with_name("static") / "operator.css"
    def app(environ: dict[str, object], start_response: Callable[..., object]) -> Iterable[bytes]:
        path = str(environ.get("PATH_INFO", "/")); method = str(environ.get("REQUEST_METHOD", "GET"))
        if method != "GET":
            start_response("405 Method Not Allowed", [("Content-Type", "text/plain; charset=utf-8"), ("Allow", "GET")])
            return ["唯讀端點，不接受此操作。".encode("utf-8")]
        if path == "/static/operator.css":
            start_response("200 OK", [("Content-Type", "text/css; charset=utf-8"), ("Cache-Control", "no-store")])
            return [css_path.read_bytes()]
        if path != "/":
            start_response("404 Not Found", [("Content-Type", "text/plain; charset=utf-8")]); return ["找不到頁面。".encode("utf-8")]
        body = render_operator_html(view_provider()).encode("utf-8")
        start_response("200 OK", [("Content-Type", "text/html; charset=utf-8"), ("Cache-Control", "no-store"), ("Content-Length", str(len(body)))])
        return [body]
    return app
