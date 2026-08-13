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


class RecoveringVerifier(FixtureVerifier):
    def __init__(self) -> None:
        super().__init__()
        self.fail = False

    def run(self, **values):
        if self.fail:
            self.calls.append(values)
            raise ConnectionError("fixture transport interruption")
        return super().run(**values)


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
    assert refresher.health.status == "READY"
    assert refresher.health.successful_refreshes == 1


def test_refresh_failure_preserves_last_good_snapshot_and_next_cycle_recovers(tmp_path) -> None:
    verifier = RecoveringVerifier()
    target = tmp_path / "live.json"
    refresher = LiveFiveTimeframeSnapshotRefresher(
        verifier,
        symbol="TMFH6",
        session=None,
        after_hours=False,
        snapshot_path=target,
    )
    assert refresher.refresh_safely() is True
    good = target.read_bytes()

    verifier.fail = True
    assert refresher.refresh_safely() is False
    assert target.read_bytes() == good
    assert refresher.health.status == "DEGRADED"
    assert refresher.health.consecutive_failures == 1
    assert refresher.health.last_failure_at is not None

    verifier.fail = False
    assert refresher.refresh_safely() is True
    assert refresher.health.status == "READY"
    assert refresher.health.consecutive_failures == 0
    assert refresher.health.successful_refreshes == 2


def test_many_consecutive_failures_do_not_publish_unverified_data(tmp_path) -> None:
    verifier = RecoveringVerifier()
    verifier.fail = True
    target = tmp_path / "live.json"
    refresher = LiveFiveTimeframeSnapshotRefresher(
        verifier,
        symbol="TMFH6",
        session=None,
        after_hours=False,
        snapshot_path=target,
    )
    for _ in range(100):
        assert refresher.refresh_safely() is False
    assert not target.exists()
    assert refresher.health.consecutive_failures == 100
    assert refresher.health.safe_payload()["status"] == "DEGRADED"


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
