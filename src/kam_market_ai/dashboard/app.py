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


class DashboardApp:
    def __init__(self, snapshot_path: str | Path = "debug/position/dashboard_position_snapshot.json", *, presenter: DashboardPresenterView | None = None, ui_config: DashboardUIConfig | None = None, adapter_config: DashboardWSGIAdapterConfig | None = None) -> None:
        self.snapshot_path = Path(snapshot_path)
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
