import json

import pytest

from kam_market_ai.dashboard.app import DashboardApp
from kam_market_ai.live_read_only.five_timeframe_snapshot import (
    read_five_timeframe_snapshot,
    write_five_timeframe_snapshot,
)


def safe_payload() -> dict[str, object]:
    return {
        "success": False,
        "status": "ATTESTATION_REQUIRED",
        "market_data_only": True,
        "trading_enabled": False,
        "live_order_allowed": False,
        "symbol": "TMFH6",
        "session": None,
        "analysis_preview": {
            "decision_status": "BLOCKED",
            "action": "HOLD",
            "three_second_summary": {"headline": "日週線形成中", "direction": "neutral"},
            "timeframes": {"5m": {"trend": "<unsafe>", "status": "ok"}},
        },
    }


def test_safe_snapshot_round_trip(tmp_path) -> None:
    path = write_five_timeframe_snapshot(tmp_path / "live.json", safe_payload())

    assert read_five_timeframe_snapshot(path) == safe_payload()
    assert not path.with_suffix(".json.tmp").exists()


@pytest.mark.parametrize("change", [
    {"trading_enabled": True},
    {"live_order_allowed": True},
    {"market_data_only": False},
    {"candles": []},
])
def test_snapshot_rejects_unsafe_or_raw_content(tmp_path, change) -> None:
    payload = {**safe_payload(), **change}
    with pytest.raises(ValueError):
        write_five_timeframe_snapshot(tmp_path / "live.json", payload)


def test_dashboard_exposes_snapshot_as_no_store_json(tmp_path) -> None:
    path = write_five_timeframe_snapshot(tmp_path / "live.json", safe_payload())
    response = {}
    body = b"".join(DashboardApp(five_timeframe_snapshot_path=path)(
        {"PATH_INFO": "/api/five-timeframe", "REQUEST_METHOD": "GET"},
        lambda status, headers: response.update(status=status, headers=dict(headers)),
    ))

    assert response["status"] == "200 OK"
    assert response["headers"]["Cache-Control"] == "no-store"
    assert json.loads(body)["analysis_preview"]["action"] == "HOLD"


def test_dashboard_fails_closed_when_snapshot_is_missing(tmp_path) -> None:
    response = {}
    body = b"".join(DashboardApp(five_timeframe_snapshot_path=tmp_path / "missing.json")(
        {"PATH_INFO": "/api/five-timeframe", "REQUEST_METHOD": "GET"},
        lambda status, headers: response.update(status=status),
    ))

    assert response["status"] == "503 Service Unavailable"
    assert json.loads(body)["status"] == "SNAPSHOT_UNAVAILABLE"


def test_dashboard_renders_safe_three_second_view_without_trade_controls(tmp_path) -> None:
    path = write_five_timeframe_snapshot(tmp_path / "live.json", safe_payload())
    response = {}
    body = b"".join(DashboardApp(five_timeframe_snapshot_path=path)(
        {"PATH_INFO": "/five-timeframe", "REQUEST_METHOD": "GET"},
        lambda status, headers: response.update(status=status),
    )).decode("utf-8")

    assert response["status"] == "200 OK"
    assert "日週線形成中" in body
    assert "TMFH6" in body
    assert "&lt;unsafe&gt;" in body
    assert "禁止真實下單" in body
    assert "place_order" not in body.lower()
