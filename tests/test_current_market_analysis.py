from datetime import UTC, datetime

import pytest

from kam_market_ai.notifications.current_market_analysis import (
    build_current_market_analysis,
    build_current_market_analysis_alert,
)


def _payload() -> dict[str, object]:
    return {
        "status": "READY_VERIFIED_FIVE_TIMEFRAMES",
        "analysis_preview": {
            "timeframes": {
                "1d": {"status": "ambiguous", "price_vs_ma60": "above"},
                "60m": {
                    "status": "ambiguous",
                    "ma20_support": "held",
                    "market_bias": "bullish",
                },
                "15m": {
                    "status": "ambiguous",
                    "price_vs_ma20": "above",
                    "ma20_direction": "rising",
                },
                "5m": {
                    "status": "ambiguous",
                    "price_vs_ma20": "above",
                    "ma20_direction": "rising",
                },
            },
            "kam_rule_decision": {
                "paper_test_direction": {"reason_code": "PAPER_TEST_ONLY"}
            },
        },
    }


def test_analysis_uses_stable_semantic_fingerprint_across_five_minute_buckets() -> None:
    payload = _payload()
    first = build_current_market_analysis(
        payload, observed_at=datetime(2026, 8, 17, 8, 1, tzinfo=UTC)
    )
    later = build_current_market_analysis(
        payload, observed_at=datetime(2026, 8, 17, 8, 6, tzinfo=UTC)
    )

    assert first.bucket != later.bucket
    assert first.fingerprint == later.fingerprint
    assert first.headline == "五週期偏多條件增強，等待模擬進場確認"
    assert "60分20MA支撐未破" in first.basis


def test_changed_market_semantics_change_fingerprint() -> None:
    payload = _payload()
    first = build_current_market_analysis(
        payload, observed_at=datetime(2026, 8, 17, 8, 1, tzinfo=UTC)
    )
    payload["analysis_preview"]["timeframes"]["5m"]["price_vs_ma20"] = "below"  # type: ignore[index]
    changed = build_current_market_analysis(
        payload, observed_at=datetime(2026, 8, 17, 8, 6, tzinfo=UTC)
    )

    assert changed.fingerprint != first.fingerprint
    assert "短線尚未同步" in changed.headline


def test_daily_descending_trendline_weakening_is_explained_in_short_setup() -> None:
    payload = _payload()
    frames = payload["analysis_preview"]["timeframes"]  # type: ignore[index]
    frames["1d"]["bullish_weakening"] = True  # type: ignore[index]
    frames["60m"]["ma20_support"] = "broken"  # type: ignore[index]
    frames["60m"]["market_bias"] = "bearish"  # type: ignore[index]
    frames["15m"]["price_vs_ma20"] = "below"  # type: ignore[index]
    frames["15m"]["ma20_direction"] = "falling"  # type: ignore[index]
    frames["5m"]["price_vs_ma20"] = "below"  # type: ignore[index]

    analysis = build_current_market_analysis(
        payload, observed_at=datetime(2026, 8, 17, 8, 1, tzinfo=UTC)
    )

    assert analysis.headline == "日線下降趨勢線確認多方轉弱，空單條件成立"
    assert "日線下降趨勢線壓制、多方轉弱" in analysis.basis
    assert analysis.fingerprint


def test_daily_rejection_headline_has_priority_when_short_is_confirmed() -> None:
    payload = _payload()
    timeframes = payload["analysis_preview"]["timeframes"]  # type: ignore[index]
    timeframes["1d"]["bullish_weakening"] = True
    timeframes["60m"].update({"ma20_support": "broken", "market_bias": "bearish"})
    timeframes["15m"].update({"price_vs_ma20": "below", "ma20_direction": "falling"})
    timeframes["5m"].update({"price_vs_ma20": "below", "ma20_direction": "falling"})

    analysis = build_current_market_analysis(
        payload, observed_at=datetime(2026, 8, 17, 8, 1, tzinfo=UTC)
    )

    assert analysis.headline == "日線下降趨勢線確認多方轉弱，空單條件成立"
    assert "日線下降趨勢線壓制、多方轉弱" in analysis.basis


def test_stale_analysis_fails_closed_and_line_alert_stays_paper_only() -> None:
    payload = _payload()
    payload["analysis_preview"]["timeframes"]["15m"]["status"] = "stale"  # type: ignore[index]
    observed_at = datetime(2026, 8, 17, 8, 1, tzinfo=UTC)
    analysis = build_current_market_analysis(payload, observed_at=observed_at)
    alert = build_current_market_analysis_alert(analysis, observed_at=observed_at)

    assert analysis.headline == "資料不足，暫停盤勢判讀"
    assert alert.live_order_allowed is False
    assert "Paper Trading" in alert.text
    assert "最多1口微台" in alert.text
    assert "不會送出真實委託" in alert.text


def test_analysis_requires_timezone_aware_clock() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        build_current_market_analysis(
            _payload(), observed_at=datetime(2026, 8, 17, 8, 1)  # noqa: DTZ001
        )
