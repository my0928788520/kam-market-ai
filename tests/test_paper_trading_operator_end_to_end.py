from datetime import UTC, datetime, time
from decimal import Decimal

from kam_market_ai.paper_trading.contracts import PaperTradingAccountSnapshot, PaperTradingRiskLimits, PaperTradingSafetyState
from kam_market_ai.paper_trading.ledger import PaperTradingLedger
from kam_market_ai.paper_trading.matching_engine import InMemoryPaperOrderBook, OfflineMarketSnapshot, PaperTradingOrderType, match_paper_trading_order
from kam_market_ai.paper_trading.operator_presenter import build_operator_presenter
from kam_market_ai.paper_trading.order_proposal import PaperOrderProposalAction, PaperOrderProposalInput, PaperOrderProposalOrderType, PaperOrderProposalReason, PaperOrderProposalRisk, PaperOrderProposalRiskStatus, build_paper_order_proposal
from kam_market_ai.paper_trading.proposal_runner import PaperOrderProposalRunnerState, confirm_paper_order_proposal


def test_offline_proposal_to_manual_confirmation_to_paper_fill_to_view() -> None:
    now = datetime(2026, 8, 13, 2, tzinfo=UTC)
    source = PaperOrderProposalInput("p", "v", "TEST", PaperOrderProposalAction.BUY, PaperOrderProposalOrderType.MARKET, Decimal("1"), Decimal("100"), None, Decimal("90"), Decimal("110"), Decimal("0.7"), PaperOrderProposalRisk(PaperOrderProposalRiskStatus.ACCEPTABLE, "ok"), (PaperOrderProposalReason("R", "reason"),), now, datetime(2026, 8, 13, 3, tzinfo=UTC), "source")
    proposed = build_paper_order_proposal(source)
    safety = PaperTradingSafetyState(True, False, (), PaperTradingAccountSnapshot((), Decimal("0"), now), PaperTradingRiskLimits(Decimal("2"), Decimal("1000"), Decimal("100"), 2, ("TEST",), (now.weekday(),), time(0), time(23, 59)))
    confirmed, request, _ = confirm_paper_order_proposal(proposed.proposal, PaperOrderProposalRunnerState(), safety, now, manual_confirmed=True)
    matched = match_paper_trading_order(request, PaperTradingOrderType.MARKET, InMemoryPaperOrderBook((OfflineMarketSnapshot("TEST", Decimal("99"), Decimal("100"), Decimal("2"), Decimal("2"), now),)), PaperTradingLedger(Decimal("1000")), safety)
    view = build_operator_presenter(confirmed, matched)
    assert matched.state.value == "filled" and view.matching["state"] == "已完成" and view.ledger["cash"] == "900"
