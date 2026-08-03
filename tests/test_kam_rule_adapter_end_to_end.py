from datetime import UTC, date, datetime, time
from decimal import Decimal
from hashlib import sha256

from kam_market_ai.paper_trading.contracts import PaperTradingAccountSnapshot, PaperTradingRiskLimits, PaperTradingSafetyState
from kam_market_ai.paper_trading.kam_rule_adapter import KamRuleAdapterInput, KamTimeframeState, build_kam_rule_proposal
from kam_market_ai.paper_trading.proposal_runner import PaperOrderProposalRunnerState, confirm_paper_order_proposal

def test_confirmed_kam_buy_uses_existing_paper_request_path():
    now=datetime(2026,8,13,1,tzinfo=UTC); h=sha256(b"x").hexdigest(); value=KamRuleAdapterInput("DEMO-TW",now,date(2026,8,13),"FRESH",Decimal("100"),KamTimeframeState("AU"),KamTimeframeState("AU"),KamTimeframeState("AU"),KamTimeframeState("AU"),KamTimeframeState("AU"),"U3",Decimal("98"),Decimal("102"),Decimal("98"),Decimal("102"),Decimal("1"),"kam-v1",h)
    decision, result, _=build_kam_rule_proposal(value); safety=PaperTradingSafetyState(True,False,(),PaperTradingAccountSnapshot((),Decimal("0"),now),PaperTradingRiskLimits(Decimal("2"),Decimal("1000"),Decimal("100"),2,("DEMO-TW",),(now.weekday(),),time(0),time(23,59)))
    _, request, _=confirm_paper_order_proposal(result.proposal,PaperOrderProposalRunnerState(),safety,now,manual_confirmed=True)
    assert decision.proposal_action.value == "buy" and request is not None and request.live_order_allowed is False
