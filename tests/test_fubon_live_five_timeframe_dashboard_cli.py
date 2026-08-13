from pathlib import Path

from kam_market_ai.market_data.fubon_live_five_timeframe_dashboard_cli import (
    LiveFiveTimeframeSnapshotRefresher,
    main,
)
from kam_market_ai.market_data.fubon_live_five_timeframe_verifier import (
    FubonLiveFiveTimeframeVerifier,
)


class FixtureVerifier(FubonLiveFiveTimeframeVerifier):
    def __init__(self) -> None:
        self.calls = []

    def run(self, **values):
        self.calls.append(values)
        return {
            "success": False,
            "status": "ATTESTATION_REQUIRED",
            "market_data_only": True,
            "trading_enabled": False,
            "live_order_allowed": False,
            "analysis_preview": {"action": "HOLD"},
        }


def test_refresher_writes_only_safe_snapshot(tmp_path) -> None:
    verifier = FixtureVerifier()
    target = tmp_path / "nested" / "live.json"
    refresher = LiveFiveTimeframeSnapshotRefresher(
        verifier,
        symbol="TMFH6",
        session=None,
        after_hours=False,
        snapshot_path=target,
    )

    payload = refresher.refresh_once()

    assert target.is_file()
    assert payload["analysis_preview"]["action"] == "HOLD"
    assert verifier.calls == [{"symbol": "TMFH6", "session": None, "after_hours": False}]


def test_service_requires_live_flag_and_loopback_host(capsys) -> None:
    assert main(["--symbol", "TMFH6"]) == 2
    assert "LIVE_FLAG_REQUIRED" in capsys.readouterr().out

    assert main([
        "--live", "--symbol", "TMFH6", "--host", "0.0.0.0",
    ]) == 2
    assert "LOCAL_SERVICE_INPUT_ERROR" in capsys.readouterr().out


def test_service_source_contains_no_order_or_account_capability() -> None:
    import kam_market_ai.market_data.fubon_live_five_timeframe_dashboard_cli as module

    source = Path(module.__file__).read_text(encoding="utf-8").lower()
    assert "place_order" not in source
    assert "accounting" not in source
