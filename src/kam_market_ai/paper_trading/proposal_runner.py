"""Manual, fail-closed proposal confirmation for the in-memory paper engine."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from .contracts import PaperTradingOrderRequest, PaperTradingSafetyState, PaperTradingSide
from .order_proposal import (
    ManualConfirmationStatus, PaperOrderProposal, PaperOrderProposalAction,
    PaperOrderProposalAuditEvent, PaperOrderProposalResult,
)


@dataclass(frozen=True, slots=True)
class PaperOrderProposalRunnerState:
    used_proposal_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.used_proposal_ids != tuple(sorted(set(self.used_proposal_ids))):
            raise ValueError("Proposal IDs must be canonical ordered.")


def confirm_paper_order_proposal(proposal: PaperOrderProposal, state: PaperOrderProposalRunnerState, safety: PaperTradingSafetyState, confirmed_at: datetime, *, manual_confirmed: bool) -> tuple[PaperOrderProposalResult, PaperTradingOrderRequest | None, PaperOrderProposalRunnerState]:
    """Convert only one explicit manual confirmation into a Phase 1 request."""
    if not isinstance(proposal, PaperOrderProposal) or not isinstance(state, PaperOrderProposalRunnerState) or not isinstance(safety, PaperTradingSafetyState):
        raise TypeError("Unsupported proposal confirmation input.")
    if confirmed_at.tzinfo is None or confirmed_at.utcoffset() != UTC.utcoffset(confirmed_at):
        raise ValueError("confirmed_at must be UTC timezone-aware.")
    codes: list[str] = []
    if proposal.input.proposal_id in state.used_proposal_ids: codes.append("DUPLICATE_PROPOSAL_ID")
    if confirmed_at >= proposal.input.expires_at: codes.append("PROPOSAL_EXPIRED")
    if proposal.input.action is PaperOrderProposalAction.HOLD: codes.append("HOLD_CANNOT_CONVERT")
    if not manual_confirmed: codes.append("MANUAL_CONFIRMATION_REQUIRED")
    if safety.emergency_stop: codes.append("EMERGENCY_STOP")
    if codes:
        status = ManualConfirmationStatus.EXPIRED if "PROPOSAL_EXPIRED" in codes else ManualConfirmationStatus.REJECTED
        result = PaperOrderProposalResult(None, status, tuple(sorted(codes)), PaperOrderProposalAuditEvent(proposal.proposal_hash, "proposal_expired" if status is ManualConfirmationStatus.EXPIRED else "proposal_rejected", confirmed_at, tuple(sorted(codes))))
        return result, None, state
    side = PaperTradingSide.BUY if proposal.input.action is PaperOrderProposalAction.BUY else PaperTradingSide.SELL
    price = proposal.input.limit_price if proposal.input.order_type.value == "limit" else proposal.input.reference_price
    request = PaperTradingOrderRequest(proposal.input.proposal_id, proposal.input.instrument, side, proposal.input.quantity, price, confirmed_at)
    next_state = PaperOrderProposalRunnerState(tuple(sorted((*state.used_proposal_ids, proposal.input.proposal_id))))
    result = PaperOrderProposalResult(proposal, ManualConfirmationStatus.CONFIRMED, (), PaperOrderProposalAuditEvent(proposal.proposal_hash, "proposal_confirmed", confirmed_at))
    return result, request, next_state
