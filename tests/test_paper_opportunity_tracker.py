from datetime import UTC, datetime, timedelta
from decimal import Decimal

from kam_market_ai.paper_trading.paper_opportunity_tracker import PaperOpportunityTracker


def test_c_grade_shadow_tracks_thresholds_and_persists_without_live_permissions(tmp_path) -> None:
    path = tmp_path / "opportunities.json"
    tracker = PaperOpportunityTracker(path)
    started = datetime(2026, 8, 19, 1, tzinfo=UTC)

    tracker.observe(grade="C", direction="SHORT", price=Decimal("45000"), observed_at=started)
    tracker.observe(grade="C", direction="SHORT", price=Decimal("44935"), observed_at=started + timedelta(seconds=3))
    tracker.observe(grade="B", direction=None, price=Decimal("44940"), observed_at=started + timedelta(seconds=6))

    summary = PaperOpportunityTracker(path).safe_payload()
    assert summary["sample_size"] == 1
    assert summary["reached_30_points"] == 1
    assert summary["reached_60_points"] == 1
    assert summary["reached_120_points"] == 0
    assert summary["dry_run"] is True
    assert summary["live_order_allowed"] is False


def test_non_c_grade_never_starts_shadow_observation() -> None:
    tracker = PaperOpportunityTracker()
    tracker.observe(
        grade="B", direction="SHORT", price=Decimal("45000"),
        observed_at=datetime(2026, 8, 19, 1, tzinfo=UTC),
    )
    assert tracker.safe_payload()["sample_size"] == 0
