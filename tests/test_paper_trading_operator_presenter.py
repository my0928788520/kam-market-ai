from datetime import UTC, datetime
from decimal import Decimal

from kam_market_ai.paper_trading.order_proposal import PaperOrderProposalAction, PaperOrderProposalInput, PaperOrderProposalOrderType, PaperOrderProposalReason, PaperOrderProposalRisk, PaperOrderProposalRiskStatus, build_paper_order_proposal
from kam_market_ai.paper_trading.operator_presenter import build_operator_presenter


def test_presenter_is_deterministic_read_only_and_html_safe() -> None:
    now = datetime(2026, 8, 13, 2, tzinfo=UTC)
    value = PaperOrderProposalInput("p", "v", "TEST", PaperOrderProposalAction.BUY, PaperOrderProposalOrderType.MARKET, Decimal("1"), Decimal("100"), None, Decimal("90"), Decimal("110"), Decimal("0.5"), PaperOrderProposalRisk(PaperOrderProposalRiskStatus.ACCEPTABLE, "<safe>"), (PaperOrderProposalReason("R", "<script>", 0),), now, datetime(2026, 8, 13, 3, tzinfo=UTC), "hash")
    view = build_operator_presenter(build_paper_order_proposal(value))
    assert view.read_only and view.dry_run and not view.live_order_allowed and not view.broker_connected
    assert view.title == "KAM 期貨模擬交易操作台"
    assert view.proposal["instrument"] == "TEST"
    assert view.proposal["action"] == "多單進場"
    assert build_operator_presenter(build_paper_order_proposal(value)) == view
