import json
from pathlib import Path

import pytest

from kam_market_ai.market_data.five_timeframe_fixture_verifier import (
    FIXTURE_ID,
    run_controlled_fixture_verification,
)
from kam_market_ai.market_data.five_timeframe_fixture_verifier_cli import main


def test_controlled_fixture_reaches_verified_ready_with_traceable_coverage() -> None:
    payload = run_controlled_fixture_verification().payload

    assert payload["status"] == "READY_VERIFIED_FIVE_TIMEFRAMES"
    assert payload["loaded_timeframes"] == ["5m", "15m", "60m", "1d", "1w"]
    assert payload["fixture_id"] == FIXTURE_ID
    assert payload["verified_trading_dates"] == ["2026-08-10", "2026-08-11"]
    assert payload["verified_week_starts"] == ["2026-08-10"]
    assert payload["external_endpoint_call_count"] == 0
    assert payload["fixture_intraday_slice_count"] == 3
    assert payload["coverage"]["1d"]["count"] == 2
    assert payload["coverage"]["1w"]["count"] == 1


def test_controlled_fixture_preserves_all_non_trading_boundaries() -> None:
    payload = run_controlled_fixture_verification().payload

    for field in (
        "network_accessed",
        "credentials_loaded",
        "account_connected",
        "broker_connected",
        "trading_enabled",
        "live_order_allowed",
        "raw_payload_retained",
    ):
        assert payload[field] is False
    assert payload["market_data_only"] is True
    assert payload["manual_trigger_only"] is True


def test_cli_emits_only_safe_json(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--fixture", FIXTURE_ID]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["success"] is True
    assert "series" not in payload and "candles" not in payload


def test_verifier_has_no_live_or_file_input_capability() -> None:
    import kam_market_ai.market_data.five_timeframe_fixture_verifier_cli as cli

    source = Path(cli.__file__).read_text(encoding="utf-8").lower()
    for forbidden in ("--live", "--env", "open(", "settings", "authorization", "provider"):
        assert forbidden not in source
