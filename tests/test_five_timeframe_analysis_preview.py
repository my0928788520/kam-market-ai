from datetime import UTC, datetime, timedelta
from types import MappingProxyType

import pytest

from kam_market_ai.live_read_only.five_timeframe_analysis_preview import (
    build_verified_five_timeframe_analysis_preview,
)
from kam_market_ai.market_data.fubon_five_timeframe_pipeline import (
    CompleteFiveTimeframeCandleResult,
    FiveTimeframe,
)
from kam_market_ai.models import Candle, Instrument

NOW = datetime(2026, 8, 13, 4, 0, tzinfo=UTC)


def complete_result() -> CompleteFiveTimeframeCandleResult:
    durations = {
        FiveTimeframe.M5: timedelta(minutes=5),
        FiveTimeframe.M15: timedelta(minutes=15),
        FiveTimeframe.M60: timedelta(hours=1),
        FiveTimeframe.DAY: timedelta(days=1),
        FiveTimeframe.WEEK: timedelta(days=7),
    }
    series = {}
    for index, (timeframe, duration) in enumerate(durations.items()):
        end = NOW - duration
        series[timeframe] = (
            Candle(Instrument.TMF, end - duration, end, 100, 103, 99, 102 + index, 10),
        )
    return CompleteFiveTimeframeCandleResult(
        instrument=Instrument.TMF,
        session=None,
        series=MappingProxyType(series),
        endpoint_call_count=3,
    )


def test_preview_runs_all_five_timeframes_and_remains_fail_closed() -> None:
    payload = build_verified_five_timeframe_analysis_preview(
        complete_result(),
        evaluated_at=NOW,
    ).safe_payload()

    assert list(payload["timeframes"]) == ["5m", "15m", "60m", "1d", "1w"]
    assert set(payload["timeframes"]["5m"]) == {
        "status", "usable", "position", "trend", "structure", "timing", "error_codes",
    }
    assert payload["decision_status"] == "BLOCKED"
    assert payload["action"] == "HOLD"
    assert "M5_ANALYSIS_ENGINE_REQUIRED" not in payload["blockers"]
    assert "TRADING_DECISION_MAPPING_NOT_APPROVED" not in payload["blockers"]
    assert payload["kam_rule_decision"]["mapping_version"] == "five-timeframe-kam-state-v1.0"
    assert set(payload["kam_rule_decision"]["states"]) == {"5m", "15m", "60m", "1d", "1w"}
    assert payload["kam_rule_decision"]["action"] == "HOLD"
    assert payload["kam_rule_decision"]["live_order_allowed"] is False
    assert payload["kam_rule_decision"]["paper_test_direction"]["direction"] in {
        "LONG", "SHORT", "HOLD"
    }
    assert payload["kam_rule_decision"]["paper_test_direction"]["live_order_allowed"] is False
    assert set(payload["decision_diagnostics"]) == {
        "direction",
        "confidence_score",
        "confidence_state",
        "alignment_state",
        "risk_score",
        "risk_level",
        "risk_state",
        "next_step",
        "next_step_state",
        "next_step_priority",
        "observation_only",
    }
    assert payload["decision_diagnostics"]["observation_only"] is True
    assert payload["three_second_summary"]["action"] == "HOLD"
    assert payload["three_second_summary"]["decision_status"] == "BLOCKED"
    assert payload["three_second_summary"]["direction"] in {"偏多", "偏空", "觀望"}
    assert payload["three_second_summary"]["direction"] == payload["kam_rule_decision"]["direction"]
    assert payload["three_second_summary"]["risk"] == payload["decision_diagnostics"]["risk_level"]
    assert payload["market_data_only"] is True
    assert payload["live_order_allowed"] is False
    assert payload["raw_candles_retained"] is False


def test_preview_rejects_unverified_or_naive_inputs() -> None:
    with pytest.raises(TypeError):
        build_verified_five_timeframe_analysis_preview(object(), evaluated_at=NOW)
    with pytest.raises(ValueError, match="timezone-aware"):
        build_verified_five_timeframe_analysis_preview(
            complete_result(),
            evaluated_at=NOW.replace(tzinfo=None),
        )
