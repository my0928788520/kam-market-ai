from datetime import UTC, date, datetime
from decimal import Decimal
from hashlib import sha256

from kam_market_ai.paper_trading.kam_rule_adapter import KamRuleAdapterInput, KamTimeframeState, build_kam_rule_proposal, evaluate_kam_rules
from kam_market_ai.paper_trading.order_proposal import PaperOrderProposalAction


NOW = datetime(2026, 8, 13, 1, tzinfo=UTC); HASH = sha256(b"fixture").hexdigest()
def _input(**changes):
    values = dict(instrument="DEMO-TW", generated_at=NOW, data_trade_date=date(2026,8,13), data_freshness="FRESH", current_price=Decimal("100"), weekly_state=KamTimeframeState("AU"), daily_state=KamTimeframeState("AU"), m60_state=KamTimeframeState("AU"), m15_state=KamTimeframeState("AU"), m5_state=KamTimeframeState("AU"), u_curve_stage="U3", downside_watch=Decimal("98"), upside_resistance=Decimal("102"), stop_loss_price=Decimal("98"), take_profit_price=Decimal("102"), quantity=Decimal("1"), strategy_version="kam-v1", source_hash=HASH)
    values.update(changes); return KamRuleAdapterInput(**values)

def test_fail_closed_priority_cases_produce_one_hold_action():
    for value in (_input(emergency_stop=True), _input(data_freshness="STALE"), _input(u_curve_stage="U0"), _input(u_curve_stage="U6"), _input(weekly_state=KamTimeframeState("BD"))):
        decision = evaluate_kam_rules(value)
        assert decision.direction == "BLOCKED" and decision.proposal_action is PaperOrderProposalAction.HOLD and len(decision.reasons) == 1

def test_bullish_gate_progression_and_hash_are_deterministic():
    assert evaluate_kam_rules(_input(m60_state=KamTimeframeState("NF"))).primary_next_action == "等待 60 分進入操作區"
    assert evaluate_kam_rules(_input(m15_state=KamTimeframeState("NF"))).primary_next_action == "等待 15 分結構確認"
    assert evaluate_kam_rules(_input(m5_state=KamTimeframeState("NF"))).primary_next_action == "等待 5 分觸發"
    first = evaluate_kam_rules(_input()); second = evaluate_kam_rules(_input())
    assert first.proposal_action is PaperOrderProposalAction.BUY and first.decision_hash == second.decision_hash

def test_hold_proposal_has_no_executable_order_fields():
    decision, proposal, _ = build_kam_rule_proposal(_input(u_curve_stage="U0"))
    assert decision.proposal_action is PaperOrderProposalAction.HOLD
    assert proposal.proposal.input.order_type is None and proposal.proposal.input.quantity is None
