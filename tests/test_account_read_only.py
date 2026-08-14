from dataclasses import FrozenInstanceError
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from kam_market_ai.account_read_only import (
    AccountDataFreshness,
    AccountFunds,
    AccountPositionSummary,
    CapitalSafetyLevel,
    CapitalSafetyThresholds,
    DEMO_MARGIN_SOURCE,
    DemoMarginRequirementSource,
    FuturesAccountSnapshot,
    MarginRequirement,
    MarginUsage,
    assess_capital_safety,
    calculate_required_margins,
)


_TIME = datetime(2026, 8, 5, tzinfo=UTC)


def test_demo_margin_snapshot_matches_current_taifex_index_requirements() -> None:
    requirements = {item.product_code: item for item in DEMO_MARGIN_SOURCE.read_requirements()}

    assert requirements["TX"].initial_margin == Decimal(701000)
    assert requirements["TX"].maintenance_margin == Decimal(538000)
    assert requirements["MTX"].initial_margin == Decimal(175250)
    assert requirements["MTX"].maintenance_margin == Decimal(134500)
    assert requirements["TMF"].initial_margin == Decimal(35050)
    assert requirements["TMF"].maintenance_margin == Decimal(26900)
    assert requirements["TMF"].effective_at == datetime(
        2026,
        8,
        12,
        5,
        45,
        tzinfo=UTC,
    )
    assert requirements["TMF"].source == "taifex-index-margin-2026-08-12"


def _margin_source(*, freshness: AccountDataFreshness = AccountDataFreshness.FRESH) -> DemoMarginRequirementSource:
    return DemoMarginRequirementSource((
        MarginRequirement("TX", Decimal("636000"), Decimal("488000"), _TIME, "fixture-margin", _TIME, freshness),
        MarginRequirement("MTX", Decimal("159000"), Decimal("122000"), _TIME, "fixture-margin", _TIME, freshness),
        MarginRequirement("TMF", Decimal("31800"), Decimal("24400"), _TIME, "fixture-margin", _TIME, freshness),
    ))


def _snapshot(
    *,
    connected: bool = True,
    freshness: AccountDataFreshness = AccountDataFreshness.FRESH,
    equity: Decimal | None = Decimal("1000000"),
    free: Decimal | None = Decimal("800000"),
    positions: tuple[AccountPositionSummary, ...] = (),
) -> FuturesAccountSnapshot:
    return FuturesAccountSnapshot(
        "測試帳戶",
        "••••-1234",
        AccountFunds(equity, free, Decimal("20"), Decimal("10"), Decimal("16"), Decimal("0"), Decimal("0")),
        MarginUsage(Decimal("0.2")),
        positions,
        "fixture",
        _TIME,
        freshness,
        account_connected=connected,
    )


def test_required_margins_include_every_product_and_absolute_position_quantity() -> None:
    positions = (
        AccountPositionSummary("TX", "大台 TX", Decimal("1"), "LONG", Decimal("0")),
        AccountPositionSummary("MTX", "小台 MTX", Decimal("-2"), "SHORT", Decimal("0")),
        AccountPositionSummary("TMF", "微台 TMF", Decimal("3"), "LONG", Decimal("0")),
    )

    assert calculate_required_margins(positions, _margin_source()) == (
        Decimal("1049400"),
        Decimal("805200"),
    )


def test_missing_stale_disconnected_or_incomplete_data_fail_closed() -> None:
    thresholds = CapitalSafetyThresholds(Decimal("0.5"), Decimal("0.75"))
    assert assess_capital_safety(_snapshot(connected=False), thresholds, _margin_source()).level is CapitalSafetyLevel.UNKNOWN
    assert assess_capital_safety(_snapshot(freshness=AccountDataFreshness.STALE), thresholds, _margin_source()).level is CapitalSafetyLevel.UNKNOWN
    assert assess_capital_safety(_snapshot(equity=None), thresholds, _margin_source()).level is CapitalSafetyLevel.UNKNOWN
    assert assess_capital_safety(_snapshot(), thresholds).level is CapitalSafetyLevel.UNKNOWN
    assert assess_capital_safety(_snapshot(), thresholds, _margin_source(freshness=AccountDataFreshness.STALE)).level is CapitalSafetyLevel.UNKNOWN


def test_danger_caution_and_safe_follow_injected_margin_policy() -> None:
    thresholds = CapitalSafetyThresholds(
        Decimal("0.5"),
        Decimal("0.75"),
        initial_margin_multiplier=Decimal("1.1"),
        minimum_free_margin=Decimal("100"),
        maximum_margin_usage_ratio=Decimal("0.9"),
        warning_buffer_amount=Decimal("10"),
    )
    position = (AccountPositionSummary("TMF", "微台 TMF", Decimal("1"), "LONG", Decimal("0")),)
    source = _margin_source()

    assert assess_capital_safety(_snapshot(equity=Decimal("24400"), free=Decimal("1"), positions=position), thresholds, source).level is CapitalSafetyLevel.DANGER
    assert assess_capital_safety(_snapshot(equity=Decimal("32000"), free=Decimal("200"), positions=position), thresholds, source).level is CapitalSafetyLevel.CAUTION
    assessment = assess_capital_safety(_snapshot(equity=Decimal("100000"), free=Decimal("50000"), positions=position), thresholds, source)
    assert assessment.level is CapitalSafetyLevel.SAFE
    assert assessment.required_initial_margin == Decimal("31800")
    assert assessment.required_maintenance_margin == Decimal("24400")
    assert assessment.distance_to_danger == Decimal("75600")


def test_thresholds_are_immutable_and_never_enable_trading() -> None:
    thresholds = CapitalSafetyThresholds(Decimal("0.5"), Decimal("0.75"))
    with pytest.raises(FrozenInstanceError):
        thresholds.warning_buffer_amount = Decimal("1")  # type: ignore[misc]
