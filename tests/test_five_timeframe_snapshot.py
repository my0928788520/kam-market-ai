import json
from datetime import UTC, datetime, timedelta

import pytest

from kam_market_ai.dashboard.app import DashboardApp
from kam_market_ai.live_read_only.five_timeframe_snapshot import (
    five_timeframe_snapshot_age_seconds,
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
            "three_second_summary": {"headline": "日週線形成中", "direction": "觀望"},
            "timeframes": {"5m": {"trend": "<unsafe>", "position": "neutral", "structure": "neutral", "timing": "waiting", "status": "ok"}},
            "kam_rule_decision": {
                "direction": "觀望",
                "primary_next_action": "等待週線與日線方向一致",
                "decision_status": "OBSERVATION_ONLY",
                "action": "HOLD",
                "mapping_version": "five-timeframe-kam-state-v1.0",
                "states": {"5m": {"code": "NF"}},
            },
        },
    }


def test_safe_snapshot_round_trip(tmp_path) -> None:
    path = write_five_timeframe_snapshot(tmp_path / "live.json", safe_payload())

    loaded = read_five_timeframe_snapshot(path)
    assert {key: loaded[key] for key in safe_payload()} == safe_payload()
    assert loaded["snapshot_schema_version"] == "1.0"
    assert five_timeframe_snapshot_age_seconds(loaded) >= 0
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
    assert "KAM 市場方向" in body
    assert "觀望" in body
    assert "唯一下一步" in body
    assert "等待週線與日線方向一致" in body
    assert "NF" in body
    assert "中性・形成中" in body
    assert "five-timeframe-kam-state-v1.0" in body
    assert '<div class="dashboard-grid">' in body
    assert '<section class="core-grid">' in body
    assert "市場轉折位置" in body
    assert "資料與安全狀態" in body
    assert "place_order" not in body.lower()


def test_dashboard_rejects_stale_snapshot(tmp_path) -> None:
    path = write_five_timeframe_snapshot(tmp_path / "live.json", safe_payload())
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["snapshot_written_at"] = (datetime.now(UTC) - timedelta(minutes=10)).isoformat()
    path.write_text(json.dumps(raw), encoding="utf-8")
    response = {}

    body = b"".join(DashboardApp(five_timeframe_snapshot_path=path)(
        {"PATH_INFO": "/api/five-timeframe", "REQUEST_METHOD": "GET"},
        lambda status, headers: response.update(status=status),
    ))

    assert response["status"] == "503 Service Unavailable"
    assert json.loads(body)["status"] == "SNAPSHOT_UNAVAILABLE"


def test_dashboard_api_exposes_read_only_paper_runtime(tmp_path) -> None:
    path = write_five_timeframe_snapshot(tmp_path / "live.json", safe_payload())
    response = {}
    runtime = {
        "session_direction_calibration": {
            "dry_run": True,
            "live_order_allowed": False,
            "groups": {"regular_LONG": {"sample_size": 7}},
        },
        "live_order_allowed": False,
        "broker_connected": False,
    }

    body = b"".join(
        DashboardApp(
            five_timeframe_snapshot_path=path,
            paper_runtime_provider=lambda: runtime,
        )(
            {"PATH_INFO": "/api/five-timeframe", "REQUEST_METHOD": "GET"},
            lambda status, headers: response.update(status=status),
        )
    )
    payload = json.loads(body)

    assert response["status"] == "200 OK"
    calibration = payload["paper_runtime"]["session_direction_calibration"]
    assert calibration["groups"]["regular_LONG"]["sample_size"] == 7
    assert calibration["live_order_allowed"] is False


def test_dashboard_api_rejects_unsafe_paper_runtime(tmp_path) -> None:
    path = write_five_timeframe_snapshot(tmp_path / "live.json", safe_payload())
    response = {}
    body = b"".join(
        DashboardApp(
            five_timeframe_snapshot_path=path,
            paper_runtime_provider=lambda: {"live_order_allowed": True},
        )(
            {"PATH_INFO": "/api/five-timeframe", "REQUEST_METHOD": "GET"},
            lambda status, headers: response.update(status=status),
        )
    )

    assert response["status"] == "503 Service Unavailable"
    assert json.loads(body)["live_order_allowed"] is False


def test_dashboard_health_endpoint_is_read_only_and_reports_degradation() -> None:
    response = {}
    body = b"".join(DashboardApp(
        five_timeframe_health_provider=lambda: {
            "status": "DEGRADED",
            "successful_refreshes": 3,
            "consecutive_failures": 2,
            "last_success_at": "2026-08-14T01:00:00+00:00",
            "last_failure_at": "2026-08-14T01:02:00+00:00",
        },
    )(
        {"PATH_INFO": "/api/five-timeframe/health", "REQUEST_METHOD": "GET"},
        lambda status, headers: response.update(status=status, headers=dict(headers)),
    ))
    payload = json.loads(body)
    assert response["status"] == "503 Service Unavailable"
    assert response["headers"]["Cache-Control"] == "no-store"
    assert payload["consecutive_failures"] == 2
    assert payload["market_data_only"] is True
    assert payload["trading_enabled"] is False
    assert payload["live_order_allowed"] is False


def test_dashboard_health_endpoint_fails_closed_without_provider() -> None:
    response = {}
    body = b"".join(DashboardApp()(
        {"PATH_INFO": "/api/five-timeframe/health", "REQUEST_METHOD": "GET"},
        lambda status, headers: response.update(status=status),
    ))
    assert response["status"] == "503 Service Unavailable"
    assert json.loads(body)["failure_stage"] == "HEALTH_UNAVAILABLE"
