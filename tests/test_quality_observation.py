from dataclasses import replace
from decimal import Decimal

from test_quality_gate import evaluation

from kam_market_ai.decision.quality_observation import (
    ShadowObservation,
    append_observation,
    summarize_outcomes,
)


def test_append_is_jsonl_and_contains_no_order_permission(tmp_path):
    result = evaluation()
    observation = ShadowObservation.from_result("obs-1", "TMF", "night", result)
    path = tmp_path / "quality.jsonl"
    append_observation(path, observation)
    text = path.read_text(encoding="utf-8")
    assert '"decision": "a_grade"' in text
    assert "live_order" not in text


def test_summary_uses_completed_a_grade_samples_and_requires_30_to_adjust():
    base = ShadowObservation.from_result("obs", "TMF", "night", evaluation())
    samples = [
        replace(base, observation_id="win", outcome_points=Decimal(10), costs_points=Decimal(1)),
        replace(base, observation_id="loss", outcome_points=Decimal(-5), costs_points=Decimal(1)),
        replace(base, observation_id="open"),
    ]
    summary = summarize_outcomes(samples)
    assert summary["sample_size"] == 2
    assert summary["win_rate"] == Decimal("50.00")
    assert summary["expectancy_points"] == Decimal("1.50")
    assert summary["adjustment_allowed"] is False
