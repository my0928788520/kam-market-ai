from __future__ import annotations

import importlib.util
import json
from pathlib import Path

from kam_market_ai.dashboard.app import DashboardApp, _number, _pnl_number, _updated_time, render_html
from kam_market_ai.dashboard.payload import build_dashboard_payload
from kam_market_ai.dashboard.position_reader import read_position_snapshot


BUILD_SPEC = importlib.util.spec_from_file_location("build_dashboard_position_snapshot", Path("tools/build_dashboard_position_snapshot.py"))
assert BUILD_SPEC and BUILD_SPEC.loader
builder = importlib.util.module_from_spec(BUILD_SPEC)
BUILD_SPEC.loader.exec_module(builder)


def snapshot(**overrides):
    value = {
        "query_success": True, "matched_rows": 1, "product_code": "MTX", "symbol_raw": "FITM",
        "expiry": "202608", "side": "SHORT", "quantity": 1, "average_price": "40461.0",
        "market_price": "40314.0000", "unrealized_pnl": "1470.0", "updated_at": "2026-07-29T00:00:00+00:00",
        "status": "SINGLE_MTX_POSITION",
    }
    value.update(overrides)
    return value


def write_snapshot(tmp_path, value):
    path = tmp_path / "position.json"
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


def test_short_position_payload_and_html(tmp_path) -> None:
    path = write_snapshot(tmp_path, snapshot())
    payload = build_dashboard_payload(path)
    assert payload["position"]["display_state"] == "POSITION"
    page = render_html(payload)
    assert "微台" in page and "空單 ×1" in page and "40,461" in page and "+1,470" in page
    assert "商品代號" in page and "唯讀" in page and "V2.3.2" in page
    assert "市場轉折位置" in page and "資料不足，位置尚未建立" in page


def test_long_position_displays_long(tmp_path) -> None:
    payload = build_dashboard_payload(write_snapshot(tmp_path, snapshot(side="LONG", unrealized_pnl="-99.5")))
    page = render_html(payload)
    assert "多單 ×1" in page and "-99.5" in page


def test_position_display_formatting_uses_compact_numbers_and_taiwan_time() -> None:
    assert _number("40461.0") == "40,461"
    assert _number("99.50") == "99.5"
    assert _pnl_number("1470.0") == "+1,470"
    assert _pnl_number("-99.5") == "-99.5"
    assert _updated_time("2026-07-29T19:51:32+00:00") == "03:51 更新"


def test_empty_never_looks_like_sync_error(tmp_path) -> None:
    position = read_position_snapshot(write_snapshot(tmp_path, {"query_success": True, "matched_rows": 0, "updated_at": "now", "status": "EMPTY"}))
    assert position["display_state"] == "EMPTY"
    page = render_html({"position": position})
    assert "目前無部位" in page


def test_failure_and_timeout_never_look_empty(tmp_path) -> None:
    for reason in ("QUERY_FAILED", "TIMEOUT"):
        payload = build_dashboard_payload(write_snapshot(tmp_path, {"query_success": False, "matched_rows": 0, "error_code": reason}))
        page = render_html(payload)
        assert payload["position"]["display_state"] == "SYNC_ERROR"
        assert "持倉同步異常" in page and "目前無部位" not in page


def test_wsgi_serves_html_and_json(tmp_path) -> None:
    app = DashboardApp(write_snapshot(tmp_path, snapshot()))
    status, headers = [], []
    def start_response(value, supplied_headers):
        status.append(value); headers.extend(supplied_headers)
    json_body = b"".join(app({"PATH_INFO": "/api/dashboard"}, start_response))
    assert status[0] == "200 OK" and json.loads(json_body)["position"]["quantity"] == 1
    status.clear(); headers.clear()
    page = b"".join(app({"PATH_INFO": "/"}, start_response)).decode("utf-8")
    assert status[0] == "200 OK" and "市場轉折位置" in page and "目前部位" in page


def test_snapshot_builder_uses_existing_parser_artifact_shape() -> None:
    normalized = {"positions": [{"source_index": 0, "product_code": "MTX", "symbol_raw": "FITM", "contract_month": "202608", "side": "SHORT", "quantity": 1, "average_price": "10", "current_price": "9", "unrealized_pnl": "1"}]}
    matched = {"matched": {"status": "SINGLE_MTX_POSITION", "positions": [{"source_indexes": [0]}]}}
    result = builder.build_snapshot(normalized, matched, query_success=True)
    assert result["product_code"] == "MTX" and result["matched_rows"] == 1
