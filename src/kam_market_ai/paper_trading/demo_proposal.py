"""Fixed proposal and in-memory matching result for the offline DEMO mode."""
from __future__ import annotations

from datetime import UTC, datetime, time
from decimal import Decimal

from .contracts import PaperTradingAccountSnapshot, PaperTradingRiskLimits, PaperTradingSafetyState
from .ledger import PaperTradingLedger
from .matching_engine import InMemoryPaperOrderBook, OfflineMarketSnapshot, PaperTradingOrderType, match_paper_trading_order
from .order_proposal import PaperOrderProposalAction, PaperOrderProposalInput, PaperOrderProposalOrderType, PaperOrderProposalReason, PaperOrderProposalRisk, PaperOrderProposalRiskStatus, build_paper_order_proposal
from .proposal_runner import PaperOrderProposalRunnerState, confirm_paper_order_proposal
from .demo_snapshot import DEMO_SNAPSHOT


def build_demo_session():
    """Return only hard-coded demonstration objects; it never reads external data."""
    now = DEMO_SNAPSHOT.snapshot_time
    proposal = build_paper_order_proposal(PaperOrderProposalInput(
        "demo-proposal-001", "demo-fixed-v1", DEMO_SNAPSHOT.instrument, PaperOrderProposalAction.BUY,
        PaperOrderProposalOrderType.MARKET, Decimal("1"), DEMO_SNAPSHOT.current_price, None,
        Decimal("98"), Decimal("102"), Decimal("0.72"),
        PaperOrderProposalRisk(PaperOrderProposalRiskStatus.ACCEPTABLE, "示範風險檢查通過"),
        (PaperOrderProposalReason("DEMO_ONLY", "示範資料，僅供流程驗收", 0),), now,
        datetime(2026, 8, 13, 2, 0, tzinfo=UTC), "demo-source-fixed-v1",
    ))
    safety = PaperTradingSafetyState(True, False, (), PaperTradingAccountSnapshot((), Decimal("0"), now), PaperTradingRiskLimits(Decimal("2"), Decimal("1000"), Decimal("100"), 2, (DEMO_SNAPSHOT.instrument,), (now.weekday(),), time(0), time(23, 59)))
    confirmed, request, _ = confirm_paper_order_proposal(proposal.proposal, PaperOrderProposalRunnerState(), safety, now, manual_confirmed=True)
    book = InMemoryPaperOrderBook((OfflineMarketSnapshot(DEMO_SNAPSHOT.instrument, Decimal("99.5"), Decimal("100"), Decimal("2"), Decimal("2"), now),))
    matching = match_paper_trading_order(request, PaperTradingOrderType.MARKET, book, PaperTradingLedger(Decimal("10000")), safety)
    return confirmed, matching
