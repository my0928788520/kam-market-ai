"""Offline, deterministic KAM-state to Paper Proposal adapter."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from hashlib import sha256
from json import dumps

from .order_proposal import (
    PaperOrderProposalAction, PaperOrderProposalInput, PaperOrderProposalOrderType,
    PaperOrderProposalReason, PaperOrderProposalRisk, PaperOrderProposalRiskStatus,
    build_paper_order_proposal,
)

KAM_RULE_ADAPTER_VERSION = "1.0"
_STATES = frozenset({"AU", "AF", "AD", "NU", "NF", "ND", "BU", "BF", "BD"})
_USTAGES = frozenset({f"U{x}" for x in range(9)})


def _hash(value: object) -> str:
    return sha256(dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


@dataclass(frozen=True, slots=True)
class KamTimeframeState:
    code: str
    def __post_init__(self) -> None:
        if self.code not in _STATES: raise ValueError("Unsupported KAM timeframe state.")


@dataclass(frozen=True, slots=True)
class KamRiskContext:
    emergency_stop: bool
    risk_blockers: tuple[str, ...] = ()
    def __post_init__(self) -> None:
        if self.risk_blockers != tuple(sorted(set(self.risk_blockers))): raise ValueError("Risk blockers must be canonical.")


@dataclass(frozen=True, slots=True)
class KamRuleReason:
    code: str
    text: str
    priority: int
    def __post_init__(self) -> None:
        if not self.code or not self.text or self.priority < 0: raise ValueError("Invalid rule reason.")


@dataclass(frozen=True, slots=True)
class KamRuleAdapterInput:
    instrument: str
    generated_at: datetime
    data_trade_date: date
    data_freshness: str
    current_price: Decimal
    weekly_state: KamTimeframeState | None
    daily_state: KamTimeframeState | None
    m60_state: KamTimeframeState
    m15_state: KamTimeframeState
    m5_state: KamTimeframeState
    u_curve_stage: str
    downside_watch: Decimal
    upside_resistance: Decimal
    stop_loss_price: Decimal
    take_profit_price: Decimal
    quantity: Decimal
    strategy_version: str
    source_hash: str
    emergency_stop: bool = False
    risk_blockers: tuple[str, ...] = ()
    def __post_init__(self) -> None:
        if not self.instrument or self.instrument != self.instrument.upper() or not self.strategy_version or len(self.source_hash) != 64: raise ValueError("Invalid KAM source identity.")
        if self.generated_at.tzinfo is None or self.generated_at.utcoffset() != UTC.utcoffset(self.generated_at): raise ValueError("generated_at must be UTC.")
        if self.data_freshness not in {"FRESH", "STALE", "INSUFFICIENT"} or self.u_curve_stage not in _USTAGES: raise ValueError("Invalid KAM state.")
        if any(not isinstance(x, Decimal) or not x.is_finite() or x <= 0 for x in (self.current_price, self.downside_watch, self.upside_resistance, self.stop_loss_price, self.take_profit_price, self.quantity)): raise ValueError("Prices and quantity must be positive Decimal.")
        if self.risk_blockers != tuple(sorted(set(self.risk_blockers))): raise ValueError("Risk blockers must be canonical.")


@dataclass(frozen=True, slots=True)
class KamRuleDecision:
    direction: str
    mtf_state: str
    u_curve_stage: str
    trend_health: str
    primary_next_action: str
    proposal_action: PaperOrderProposalAction
    confidence: Decimal
    reasons: tuple[KamRuleReason, ...]
    blockers: tuple[str, ...]
    generated_at: datetime
    source_hash: str
    def __post_init__(self) -> None:
        if self.reasons != tuple(sorted(self.reasons, key=lambda x: (x.priority, x.code, x.text))) or self.blockers != tuple(sorted(set(self.blockers))): raise ValueError("Decision fields must be canonical.")
    @property
    def decision_hash(self) -> str:
        return _hash({"direction":self.direction,"mtf_state":self.mtf_state,"u":self.u_curve_stage,"health":self.trend_health,"next":self.primary_next_action,"action":self.proposal_action.value,"confidence":str(self.confidence),"reasons":[(x.code,x.text,x.priority) for x in self.reasons],"blockers":self.blockers,"generated_at":self.generated_at.isoformat(),"source_hash":self.source_hash})


@dataclass(frozen=True, slots=True)
class KamRuleAuditEvent:
    decision_hash: str
    occurred_at: datetime
    event_type: str = "kam_rule_evaluated"


@dataclass(frozen=True, slots=True)
class KamReadOnlyDecision:
    """Non-executable KAM interpretation of five canonical timeframe states."""

    direction: str
    primary_next_action: str
    timeframe_states: tuple[str, ...]
    blockers: tuple[str, ...]
    decision_status: str = "OBSERVATION_ONLY"
    action: str = "HOLD"
    market_data_only: bool = True
    live_order_allowed: bool = False

    def safe_payload(self) -> dict[str, object]:
        return {
            "direction": self.direction,
            "primary_next_action": self.primary_next_action,
            "timeframe_states": list(self.timeframe_states),
            "blockers": list(self.blockers),
            "decision_status": self.decision_status,
            "action": self.action,
            "market_data_only": self.market_data_only,
            "live_order_allowed": self.live_order_allowed,
        }


def evaluate_kam_read_only_states(
    weekly: KamTimeframeState,
    daily: KamTimeframeState,
    m60: KamTimeframeState,
    m15: KamTimeframeState,
    m5: KamTimeframeState,
) -> KamReadOnlyDecision:
    """Evaluate mapped states without constructing an order proposal."""
    states = (weekly, daily, m60, m15, m5)
    if not all(isinstance(item, KamTimeframeState) for item in states):
        raise TypeError("five KamTimeframeState values are required")
    codes = tuple(item.code for item in states)
    higher = tuple(code[0] for code in codes[:2])
    blockers: list[str] = []

    if any(code[1] == "D" for code in codes):
        direction = "觀望"
        next_action = "等待失效週期資料恢復"
        blockers.append("DEGRADED_TIMEFRAME_STATE")
    elif higher == ("A", "A"):
        direction = "偏多"
        first_unready = next((index for index, code in enumerate(codes) if code != "AU"), None)
        labels = ("週線", "日線", "60 分", "15 分", "5 分")
        next_action = (
            "五週期偏多一致，等待人工確認"
            if first_unready is None
            else f"等待{labels[first_unready]}偏多狀態確認"
        )
    elif higher == ("B", "B"):
        direction = "偏空"
        next_action = "等待空方策略核准，維持觀望"
        blockers.append("SHORT_STRATEGY_NOT_APPROVED")
    else:
        direction = "觀望"
        next_action = "等待週線與日線方向一致"
        blockers.append("HIGHER_TIMEFRAME_NOT_ALIGNED")

    return KamReadOnlyDecision(
        direction,
        next_action,
        codes,
        tuple(blockers),
    )


def evaluate_kam_rules(value: KamRuleAdapterInput) -> KamRuleDecision:
    """Apply fixed precedence; never infer a trade from short-term state alone."""
    if not isinstance(value, KamRuleAdapterInput): raise TypeError("KamRuleAdapterInput is required.")
    blockers = list(value.risk_blockers); reasons: list[KamRuleReason] = []
    action, direction, next_action, mtf = PaperOrderProposalAction.HOLD, "NEUTRAL", "等待大方向清楚", "MTF0"
    if value.emergency_stop: blockers.append("EMERGENCY_STOP")
    elif value.data_freshness != "FRESH": blockers.append("DATA_NOT_FRESH")
    elif value.weekly_state is None or value.daily_state is None: blockers.append("HIGHER_TIMEFRAME_MISSING")
    elif value.u_curve_stage == "U0": blockers.append("U0_INSUFFICIENT")
    elif value.u_curve_stage in {"U5", "U6", "U7"}: blockers.append("U_CURVE_SHORT_MODULE_UNCONFIRMED")
    elif value.weekly_state.code.startswith("B") or value.daily_state.code.startswith("B"): blockers.append("BEARISH_WITHOUT_SHORT_STRATEGY")
    elif value.stop_loss_price >= value.current_price or value.take_profit_price <= value.current_price: blockers.append("BUY_PROTECTION_INVALID")
    if blockers:
        reasons.append(KamRuleReason(blockers[0], "規則阻擋，維持觀望。", 0)); return KamRuleDecision("BLOCKED", "MTF0", value.u_curve_stage, "轉弱", "觀望，不建立模擬委託", action, Decimal("0"), tuple(reasons), tuple(sorted(set(blockers))), value.generated_at, value.source_hash)
    direction = "BULLISH"; health = "健康"
    if not value.weekly_state.code.startswith("A") or not value.daily_state.code.startswith("A"):
        next_action, mtf = "等待大方向清楚", "MTF1"
    elif not value.m60_state.code.startswith("A"):
        next_action, mtf = "等待 60 分進入操作區", "MTF4"
    elif not value.m15_state.code.startswith("A"):
        next_action, mtf = "等待 15 分結構確認", "MTF6"
    elif not value.m5_state.code.startswith("A"):
        next_action, mtf = "等待 5 分觸發", "MTF8"
    else:
        action, next_action, mtf = PaperOrderProposalAction.BUY, "Proposal 可供人工確認", "MTF9"
    reasons.append(KamRuleReason(mtf, next_action, 0))
    return KamRuleDecision(direction, mtf, value.u_curve_stage, health, next_action, action, Decimal("0.72") if action is PaperOrderProposalAction.BUY else Decimal("0.4"), tuple(reasons), (), value.generated_at, value.source_hash)


def decision_to_paper_proposal_input(decision: KamRuleDecision, value: KamRuleAdapterInput) -> PaperOrderProposalInput:
    if decision.proposal_action is PaperOrderProposalAction.HOLD:
        return PaperOrderProposalInput(decision.decision_hash[:32], value.strategy_version, value.instrument, PaperOrderProposalAction.HOLD, None, None, value.current_price, None, None, None, decision.confidence, PaperOrderProposalRisk(PaperOrderProposalRiskStatus.BLOCKED if decision.blockers else PaperOrderProposalRiskStatus.CAUTION, decision.primary_next_action, bool(decision.blockers)), tuple(PaperOrderProposalReason(x.code,x.text,x.priority) for x in decision.reasons), value.generated_at, value.generated_at+timedelta(minutes=15), decision.decision_hash)
    return PaperOrderProposalInput(decision.decision_hash[:32], value.strategy_version, value.instrument, decision.proposal_action, PaperOrderProposalOrderType.MARKET, value.quantity, value.current_price, None, value.stop_loss_price, value.take_profit_price, decision.confidence, PaperOrderProposalRisk(PaperOrderProposalRiskStatus.ACCEPTABLE, decision.primary_next_action), tuple(PaperOrderProposalReason(x.code,x.text,x.priority) for x in decision.reasons), value.generated_at, value.generated_at+timedelta(minutes=15), decision.decision_hash)


def build_kam_rule_proposal(value: KamRuleAdapterInput):
    decision = evaluate_kam_rules(value)
    return decision, build_paper_order_proposal(decision_to_paper_proposal_input(decision, value)), KamRuleAuditEvent(decision.decision_hash, value.generated_at)
