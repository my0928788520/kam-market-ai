from datetime import UTC, datetime
from decimal import Decimal

import pytest

from kam_market_ai.paper_trading.order_proposal import (
    ManualConfirmationStatus, PaperOrderProposalAction, PaperOrderProposalInput,
    PaperOrderProposalOrderType, PaperOrderProposalReason, PaperOrderProposalRisk,
    PaperOrderProposalRiskStatus, build_paper_order_proposal,
)


NOW = datetime(2026, 8, 13, 2, tzinfo=UTC)


def _input(action: PaperOrderProposalAction = PaperOrderProposalAction.BUY) -> PaperOrderProposalInput:
    hold = action is PaperOrderProposalAction.HOLD
    return PaperOrderProposalInput(
        "proposal-1", "strategy-1", "TEST", action,
        None if hold else PaperOrderProposalOrderType.MARKET,
        None if hold else Decimal("1"), Decimal("100"), None,
        None if hold else Decimal("90"), None if hold else Decimal("110"), Decimal("0.8"),
        PaperOrderProposalRisk(PaperOrderProposalRiskStatus.ACCEPTABLE, "offline risk checked"),
        (PaperOrderProposalReason("A", "reason", 0),), NOW, datetime(2026, 8, 13, 3, tzinfo=UTC), "source-hash",
    )


def test_proposal_is_immutable_deterministic_and_canonical() -> None:
    first = build_paper_order_proposal(_input())
    second = build_paper_order_proposal(_input())
    assert first.proposal is not None
    assert first.proposal.proposal_hash == second.proposal.proposal_hash
    assert first.status is ManualConfirmationStatus.REQUIRED
    assert first.proposal.canonical_payload()["live_order_allowed"] is False
    with pytest.raises(Exception):
        first.proposal.proposal_version = "bad"  # type: ignore[misc]


def test_hold_has_no_order_and_cannot_contain_execution_fields() -> None:
    result = build_paper_order_proposal(_input(PaperOrderProposalAction.HOLD))
    assert result.status is ManualConfirmationStatus.NOT_APPLICABLE
    with pytest.raises(ValueError, match="HOLD"):
        PaperOrderProposalInput("x", "s", "TEST", PaperOrderProposalAction.HOLD, PaperOrderProposalOrderType.MARKET, Decimal("1"), Decimal("1"), None, None, None, Decimal("0"), PaperOrderProposalRisk(PaperOrderProposalRiskStatus.ACCEPTABLE, "ok"), (PaperOrderProposalReason("R", "r"),), NOW, datetime(2026, 8, 13, 3, tzinfo=UTC), "h")


def test_invalid_protection_prices_fail_closed() -> None:
    with pytest.raises(ValueError, match="BUY protection"):
        value = _input()
        PaperOrderProposalInput(value.proposal_id, value.strategy_version, value.instrument, value.action, value.order_type, value.quantity, value.reference_price, value.limit_price, Decimal("101"), value.take_profit_price, value.confidence, value.risk, value.reasons, value.generated_at, value.expires_at, value.source_hash)
