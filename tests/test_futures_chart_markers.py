from datetime import UTC, datetime
from decimal import Decimal

import pytest

from kam_market_ai.paper_trading.futures_chart_markers import (
    FuturesPaperChartMarker,
    FuturesPaperMarkerAction,
    sort_futures_paper_markers,
)


NOW = datetime(2026, 8, 25, 23, 45, tzinfo=UTC)


@pytest.mark.parametrize(
    ("action", "label"),
    (
        (FuturesPaperMarkerAction.LONG_ENTRY, "多單進場"),
        (FuturesPaperMarkerAction.LONG_EXIT, "平多"),
        (FuturesPaperMarkerAction.SHORT_ENTRY, "空單進場"),
        (FuturesPaperMarkerAction.SHORT_COVER, "回補"),
    ),
)
def test_futures_marker_uses_unambiguous_action_label(action, label) -> None:
    marker = FuturesPaperChartMarker(
        "TMFI6", NOW, Decimal("45336"), Decimal("1"), action, f"event-{action.value}"
    )

    assert marker.label == label
    assert marker.dry_run is True
    assert marker.live_order_allowed is False
    assert marker.broker_connected is False
    assert marker.canonical_payload()["label"] == label
    assert len(marker.marker_id) == 64


def test_futures_marker_rejects_any_live_execution_flag() -> None:
    with pytest.raises(ValueError, match="Paper Trading only"):
        FuturesPaperChartMarker(
            "TMFI6",
            NOW,
            Decimal("45336"),
            Decimal("1"),
            FuturesPaperMarkerAction.LONG_ENTRY,
            "event-1",
            live_order_allowed=True,
        )


def test_marker_order_is_deterministic_and_duplicate_evidence_fails_closed() -> None:
    later = FuturesPaperChartMarker(
        "TMFI6",
        NOW,
        Decimal("45336"),
        Decimal("1"),
        FuturesPaperMarkerAction.SHORT_ENTRY,
        "event-2",
    )
    earlier = FuturesPaperChartMarker(
        "TMFI6",
        datetime(2026, 8, 25, 23, 40, tzinfo=UTC),
        Decimal("45340"),
        Decimal("1"),
        FuturesPaperMarkerAction.LONG_EXIT,
        "event-1",
    )

    assert sort_futures_paper_markers((later, earlier)) == (earlier, later)
    with pytest.raises(ValueError, match="duplicate"):
        sort_futures_paper_markers((later, later))
