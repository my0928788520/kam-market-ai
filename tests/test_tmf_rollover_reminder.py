from datetime import UTC, datetime

from kam_market_ai.notifications.tmf_rollover_reminder import (
    build_due_tmf_rollover_alert,
    next_tmf_rollover,
    third_wednesday,
)


def test_third_wednesday_matches_august_2026_tmf_expiry_calendar() -> None:
    assert third_wednesday(2026, 8).date().isoformat() == "2026-08-19"


def test_advance_reminder_is_due_without_live_order_capability() -> None:
    alert = build_due_tmf_rollover_alert(
        datetime(2026, 8, 15, 2, 0, tzinfo=UTC),
        symbol="TMFH6",
    )

    assert alert is not None
    assert "提前提醒" in alert.text
    assert "2026-08-19" in alert.text
    assert "13:30" in alert.text
    assert "沒有盤後交易" in alert.text
    assert alert.live_order_allowed is False


def test_reminder_stages_have_stable_distinct_identities() -> None:
    advance = build_due_tmf_rollover_alert(
        datetime(2026, 8, 15, 2, 0, tzinfo=UTC), symbol="TMFH6"
    )
    eve = build_due_tmf_rollover_alert(
        datetime(2026, 8, 18, 2, 0, tzinfo=UTC), symbol="TMFH6"
    )
    day_of = build_due_tmf_rollover_alert(
        datetime(2026, 8, 19, 0, 0, tzinfo=UTC), symbol="TMFH6"
    )

    assert advance is not None and eve is not None and day_of is not None
    assert len({advance.proposal_hash, eve.proposal_hash, day_of.proposal_hash}) == 3


def test_after_expiry_cutoff_selects_next_month() -> None:
    value = next_tmf_rollover(datetime(2026, 8, 19, 6, 0, tzinfo=UTC))

    assert value.date().isoformat() == "2026-09-16"


def test_no_reminder_outside_seven_day_window() -> None:
    assert (
        build_due_tmf_rollover_alert(
            datetime(2026, 8, 1, 2, 0, tzinfo=UTC), symbol="TMFH6"
        )
        is None
    )
