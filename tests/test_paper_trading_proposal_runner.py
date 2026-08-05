from datetime import UTC, datetime, time
from decimal import Decimal

from kam_market_ai.paper_trading.contracts import PaperTradingAccountSnapshot, PaperTradingRiskLimits, PaperTradingSafetyState
from kam_market_ai.paper_trading.order_proposal import PaperOrderProposalAction, PaperOrderProposalInput, PaperOrderProposalOrderType, PaperOrderProposalReason, PaperOrderProposalRisk, PaperOrderProposalRiskStatus, build_paper_order_proposal
from kam_market_ai.paper_trading.proposal_runner import PaperOrderProposalRunnerState, confirm_paper_order_proposal


NOW = datetime(2026, 8, 13, 2, tzinfo=UTC)


def _proposal():
    value = PaperOrderProposalInput("proposal", "strategy", "TEST", PaperOrderProposalAction.BUY, PaperOrderProposalOrderType.MARKET, Decimal("1"), Decimal("100"), None, Decimal("90"), Decimal("110"), Decimal("0.9"), PaperOrderProposalRisk(PaperOrderProposalRiskStatus.ACCEPTABLE, "ok"), (PaperOrderProposalReason("R", "reason"),), NOW, datetime(2026, 8, 13, 3, tzinfo=UTC), "source")
    return build_paper_order_proposal(value).proposal


def _safety(stopped: bool = False) -> PaperTradingSafetyState:
    return PaperTradingSafetyState(True, stopped, (), PaperTradingAccountSnapshot((), Decimal("0"), NOW), PaperTradingRiskLimits(Decimal("10"), Decimal("10000"), Decimal("100"), 2, ("TEST",), (NOW.weekday(),), time(0), time(23, 59)))


def test_only_explicit_manual_confirmation_creates_phase_one_request() -> None:
    proposal = _proposal()
    result, request, state = confirm_paper_order_proposal(proposal, PaperOrderProposalRunnerState(), _safety(), NOW, manual_confirmed=True)
    assert result.status.value == "confirmed"
    assert request is not None and request.idempotency_key == "proposal"
    assert state.used_proposal_ids == ("proposal",)


def test_unconfirmed_duplicate_expired_and_emergency_proposals_fail_closed() -> None:
    proposal = _proposal()
    pending, request, _ = confirm_paper_order_proposal(proposal, PaperOrderProposalRunnerState(), _safety(), NOW, manual_confirmed=False)
    assert request is None and "MANUAL_CONFIRMATION_REQUIRED" in pending.reason_codes
    duplicate, _, _ = confirm_paper_order_proposal(proposal, PaperOrderProposalRunnerState(("proposal",)), _safety(), NOW, manual_confirmed=True)
    assert "DUPLICATE_PROPOSAL_ID" in duplicate.reason_codes
    stopped, _, _ = confirm_paper_order_proposal(proposal, PaperOrderProposalRunnerState(), _safety(True), NOW, manual_confirmed=True)
    assert "EMERGENCY_STOP" in stopped.reason_codes
