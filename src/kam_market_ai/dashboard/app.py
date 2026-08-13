"""Small standard-library WSGI Dashboard application."""

from __future__ import annotations

import html
import json
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Callable
from zoneinfo import ZoneInfo

from .payload import build_dashboard_payload
from .presenter import DashboardPresenterView
from .ui_contract import DashboardUIConfig, render_dashboard_ui
from .wsgi_adapter import DashboardWSGIAdapterConfig, build_dashboard_wsgi_context
from kam_market_ai.live_read_only.five_timeframe_snapshot import (
    five_timeframe_snapshot_age_seconds,
    read_five_timeframe_snapshot,
)


_STATIC = Path(__file__).with_name("static")


def _number(value: object) -> str:
    if value is None:
        return "—"
    try:
        decimal_value = Decimal(str(value))
        return format(decimal_value.normalize(), ",f")
    except (InvalidOperation, ValueError):
        return "—"


def _pnl_number(value: object) -> str:
    if value is None:
        return "—"
    try:
        decimal_value = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return "—"
    formatted = _number(decimal_value)
    return f"+{formatted}" if decimal_value > 0 else formatted


def _updated_time(value: object) -> str:
    if not value:
        return "—"
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return "—"
    if parsed.tzinfo is None:
        return "—"
    return f"{parsed.astimezone(ZoneInfo('Asia/Taipei')):%H:%M} 更新"


def _position_html(position: dict[str, object]) -> str:
    state = position["display_state"]
    if state == "SYNC_ERROR":
        return '<section class="card position error"><h2>目前部位</h2><p class="headline">持倉同步異常</p><p class="detail">狀態：' + html.escape(str(position["error_code"])) + "</p></section>"
    if state == "EMPTY":
        return '<section class="card position"><h2>目前部位</h2><p class="headline">目前無部位</p><p class="detail">同步成功</p></section>'
    product = "微台" if position["product_code"] == "MTX" else str(position["product_code"])
    side = "多單" if position["side"] == "LONG" else "空單" if position["side"] == "SHORT" else "未知方向"
    return """<section class="card position ok">
<h2>目前部位</h2><p class="position-label">我的部位</p><p class="headline">{product}</p><p class="side">{side} ×{quantity}</p>
<dl class="position-facts"><dt>均價</dt><dd>{average}</dd><dt>未實現</dt><dd class="pnl">{pnl}</dd></dl><p class="updated">{updated}</p>
</section>""".format(
        product=html.escape(product), side=html.escape(side), quantity=html.escape(str(position["quantity"])),
        average=html.escape(_number(position["average_price"])), pnl=html.escape(_pnl_number(position["unrealized_pnl"])),
        updated=html.escape(_updated_time(position["updated_at"])),
    )


def render_html(payload: dict[str, object]) -> str:
    position = payload["position"]
    assert isinstance(position, dict)
    symbol = position.get("symbol_raw") or "—"
    updated = _updated_time(position.get("updated_at"))
    top_status = """<header class="status-bar"><div class="brand">空明・市場覺察</div>
<dl class="status-meta"><div><dt>商品代號</dt><dd>{symbol}</dd></div><div><dt>最新資料時間</dt><dd>{updated}</dd></div><div><dt>市場狀態</dt><dd>資料不足</dd></div><div><dt>模式</dt><dd>唯讀</dd></div><div><dt>版本</dt><dd>V2.3.2</dd></div></dl></header>""".format(
        symbol=html.escape(str(symbol)), updated=html.escape(updated)
    )
    core_cards = """<section class="card static market-direction"><h2>市場方向</h2><p>—</p></section>
<section class="card static market-control"><h2>市場控制權</h2><p>—</p></section>
<section class="card turning-position"><h2>市場轉折位置</h2><div class="turning-content"><svg viewBox="0 0 240 72" role="img" aria-label="市場轉折位置靜態倒 U 圖"><path d="M10,64 C58,64 65,10 120,10 C175,10 182,64 230,64" /></svg><dl class="turning-details"><div><dt>起漲點</dt><dd>—</dd></div><div><dt>起跌點</dt><dd>—</dd></div><div><dt>目前位置</dt><dd>—</dd></div><div><dt>階段名稱</dt><dd>資料不足</dd></div><div><dt>下一確認條件</dt><dd>—</dd></div></dl></div><p class="detail">資料不足，位置尚未建立</p></section>"""
    timeframe_cards = "".join(
        f'<section class="card static timeframe"><h2>{label}</h2><p>—</p></section>'
        for label in ("週線", "日線", "60 分", "15 分", "5 分")
    )
    decision_cards = '<section class="card static trend-health"><h2>趨勢健康度</h2><p>—</p></section>' + _position_html(position) + '<section class="card static next-step"><h2>下一步</h2><p>—</p></section>'
    return """<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>空明・市場覺察</title><link rel="stylesheet" href="/static/dashboard.css"></head>
<body><main>{top_status}<div class="dashboard-grid"><section class="core-grid">{core_cards}</section><section class="timeframe-grid">{timeframe_cards}</section><section class="decision-grid">{decision_cards}</section></div></main></body></html>""".format(top_status=top_status, core_cards=core_cards, timeframe_cards=timeframe_cards, decision_cards=decision_cards)


def render_five_timeframe_html(payload: dict[str, object]) -> str:
    """Render only the allow-listed safe live analysis projection."""
    preview = payload.get("analysis_preview")
    preview = preview if isinstance(preview, dict) else {}
    summary = preview.get("three_second_summary")
    summary = summary if isinstance(summary, dict) else {}
    diagnostics = preview.get("decision_diagnostics")
    diagnostics = diagnostics if isinstance(diagnostics, dict) else {}
    timeframes = preview.get("timeframes")
    timeframes = timeframes if isinstance(timeframes, dict) else {}
    kam = preview.get("kam_rule_decision")
    kam = kam if isinstance(kam, dict) else {}
    kam_states = kam.get("states")
    kam_states = kam_states if isinstance(kam_states, dict) else {}

    def text(value: object) -> str:
        return html.escape(str(value if value is not None else "—"))

    cards = []
    labels = {"5m": "5 分", "15m": "15 分", "60m": "60 分", "1d": "日線", "1w": "週線"}
    state_labels = {
        "AU": "偏多・已確認", "AF": "偏多・形成中", "AD": "偏多・資料失效",
        "NU": "中性・已確認", "NF": "中性・形成中", "ND": "中性・資料失效",
        "BU": "偏空・已確認", "BF": "偏空・形成中", "BD": "偏空・資料失效",
    }
    for key in ("5m", "15m", "60m", "1d", "1w"):
        frame = timeframes.get(key)
        frame = frame if isinstance(frame, dict) else {}
        state = kam_states.get(key)
        state = state if isinstance(state, dict) else {}
        code = state.get("code")
        state_text = state_labels.get(str(code), "尚未判讀")
        cards.append(
            f'<section class="card timeframe"><h2>{labels[key]}</h2>'
            f'<p class="kam-state"><strong>{text(code)}</strong><span>{text(state_text)}</span></p>'
            f'<p>趨勢 {text(frame.get("trend"))} · 位置 {text(frame.get("position"))}</p>'
            f'<p>結構 {text(frame.get("structure"))} · 時機 {text(frame.get("timing"))}</p>'
            f'<small>資料狀態：{text(frame.get("status"))}</small></section>'
        )
    return f'''<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="refresh" content="60"><title>空明・五週期市場覺察</title><link rel="stylesheet" href="/static/dashboard.css"></head><body><main>
<header class="status-bar"><div class="brand">空明・五週期市場覺察</div><dl class="status-meta"><div><dt>商品</dt><dd>{text(payload.get("symbol"))}</dd></div><div><dt>盤別</dt><dd>{text(payload.get("session") or "日盤")}</dd></div><div><dt>資料狀態</dt><dd>{text(payload.get("status"))}</dd></div><div><dt>模式</dt><dd>唯讀觀察</dd></div></dl></header>
<section class="card market-direction"><h1>{text(summary.get("headline", "等待資料"))}</h1><p>{text(summary.get("message"))}</p></section>
<section class="decision-grid"><section class="card"><h2>KAM 市場方向</h2><p class="headline">{text(kam.get("direction", summary.get("direction")))}</p></section><section class="card"><h2>信心</h2><p class="headline">{text(summary.get("confidence"))}</p></section><section class="card"><h2>風險</h2><p class="headline">{text(summary.get("risk"))}</p></section><section class="card next-step"><h2>唯一下一步</h2><p class="headline">{text(kam.get("primary_next_action", summary.get("next_step")))}</p></section></section>
<section class="timeframe-grid">{''.join(cards)}</section>
<section class="card"><h2>安全狀態</h2><p>決策 {text(kam.get("decision_status", preview.get("decision_status")))} · 動作 {text(kam.get("action", preview.get("action")))} · 觀察模式 {text(diagnostics.get("observation_only"))}</p><p>唯讀分析・禁止真實下單・映射版本 {text(kam.get("mapping_version"))}</p></section>
</main></body></html>'''


class DashboardApp:
    def __init__(self, snapshot_path: str | Path = "debug/position/dashboard_position_snapshot.json", *, five_timeframe_snapshot_path: str | Path | None = None, five_timeframe_max_age_seconds: int = 180, presenter: DashboardPresenterView | None = None, ui_config: DashboardUIConfig | None = None, adapter_config: DashboardWSGIAdapterConfig | None = None) -> None:
        self.snapshot_path = Path(snapshot_path)
        self.five_timeframe_snapshot_path = Path(five_timeframe_snapshot_path) if five_timeframe_snapshot_path else None
        if five_timeframe_max_age_seconds <= 0:
            raise ValueError("five_timeframe_max_age_seconds must be positive")
        self.five_timeframe_max_age_seconds = five_timeframe_max_age_seconds
        self.presenter = presenter
        self.ui_config = ui_config or DashboardUIConfig.provisional()
        self.adapter_config = adapter_config or DashboardWSGIAdapterConfig.provisional()

    def __call__(self, environ: dict[str, object], start_response: Callable) -> list[bytes]:
        path = str(environ.get("PATH_INFO", "/"))
        if str(environ.get("REQUEST_METHOD", "GET")).upper() != "GET":
            body = b"Method Not Allowed"
            start_response("405 Method Not Allowed", [("Content-Type", "text/plain; charset=utf-8"), ("Content-Length", str(len(body)))])
            return [body]
        if path == "/api/dashboard":
            body = json.dumps(build_dashboard_payload(self.snapshot_path), ensure_ascii=False).encode("utf-8")
            start_response("200 OK", [("Content-Type", "application/json; charset=utf-8"), ("Content-Length", str(len(body)))])
            return [body]
        if path == "/api/five-timeframe":
            try:
                if self.five_timeframe_snapshot_path is None:
                    raise FileNotFoundError
                payload = read_five_timeframe_snapshot(self.five_timeframe_snapshot_path)
                if five_timeframe_snapshot_age_seconds(payload) > self.five_timeframe_max_age_seconds:
                    raise ValueError("STALE_FIVE_TIMEFRAME_SNAPSHOT")
                status = "200 OK"
            except (OSError, TypeError, ValueError, json.JSONDecodeError):
                payload = {
                    "success": False,
                    "status": "SNAPSHOT_UNAVAILABLE",
                    "market_data_only": True,
                    "trading_enabled": False,
                    "live_order_allowed": False,
                }
                status = "503 Service Unavailable"
            body = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
            start_response(status, [("Content-Type", "application/json; charset=utf-8"), ("Cache-Control", "no-store"), ("Content-Length", str(len(body)))])
            return [body]
        if path == "/five-timeframe":
            try:
                if self.five_timeframe_snapshot_path is None:
                    raise FileNotFoundError
                payload = read_five_timeframe_snapshot(self.five_timeframe_snapshot_path)
                if five_timeframe_snapshot_age_seconds(payload) > self.five_timeframe_max_age_seconds:
                    raise ValueError("STALE_FIVE_TIMEFRAME_SNAPSHOT")
                body = render_five_timeframe_html(payload).encode("utf-8")
                status = "200 OK"
            except (OSError, TypeError, ValueError, json.JSONDecodeError):
                body = b"Five-timeframe snapshot unavailable"
                status = "503 Service Unavailable"
            start_response(status, [("Content-Type", "text/html; charset=utf-8"), ("Cache-Control", "no-store"), ("Content-Length", str(len(body)))])
            return [body]
        if path == "/static/dashboard.css":
            body = (_STATIC / "dashboard.css").read_bytes()
            start_response("200 OK", [("Content-Type", "text/css; charset=utf-8"), ("Content-Length", str(len(body)))])
            return [body]
        if path == "/":
            if self.presenter is not None:
                try:
                    response = build_dashboard_wsgi_context(self.presenter, self.adapter_config)
                    template_context = dict(response["template_context"])
                    template_context["adapter_version"] = response.get("adapter_version", "—")
                    page = render_dashboard_ui(template_context, self.ui_config)
                    body = page.encode("utf-8")
                    headers = list(response["headers"]) + [("Content-Length", str(len(body)))]
                    start_response("200 OK", headers)
                    return [body]
                except Exception:
                    body = b"Dashboard rendering unavailable"
                    start_response("500 Internal Server Error", [("Content-Type", "text/plain; charset=utf-8"), ("Cache-Control", "no-store"), ("Content-Length", str(len(body)))])
                    return [body]
            body = render_html(build_dashboard_payload(self.snapshot_path)).encode("utf-8")
            start_response("200 OK", [("Content-Type", "text/html; charset=utf-8"), ("Content-Length", str(len(body)))])
            return [body]
        body = b"Not Found"
        start_response("404 Not Found", [("Content-Type", "text/plain; charset=utf-8"), ("Content-Length", str(len(body)))])
        return [body]
