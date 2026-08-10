"""Fail-closed KAM trade-quality gate for shadow observation only.

The gate ranks opportunities; it never creates or executes an order.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from enum import StrEnum

from .decision_confidence import DecisionConfidenceResult, TimeframeAlignmentState
from .risk_engine import RiskOperationalState, RiskResult

QUALITY_GATE_VERSION = "1.0"
ZERO = Decimal(0)
HUNDRED = Decimal(100)


class MarketRegime(StrEnum):
    TREND = "trend"
    RANGE = "range"
    HIGH_VOLATILITY = "high_volatility"
    EVENT = "event"
    UNKNOWN = "unknown"


class QualityDecision(StrEnum):
    A_GRADE = "a_grade"
    WAIT = "wait"
    BLOCK = "block"


class QualityReason(StrEnum):
    TREND_REGIME = "trend_regime"
    TIMEFRAMES_ALIGNED = "timeframes_aligned"
    LOCATION_ACCEPTABLE = "location_acceptable"
    REWARD_RISK_ACCEPTABLE = "reward_risk_acceptable"
    VOLATILITY_ACCEPTABLE = "volatility_acceptable"
    DATA_FRESH = "data_fresh"
    RISK_ACCEPTABLE = "risk_acceptable"
    REGIME_BLOCKED = "regime_blocked"
    TIMEFRAME_CONFLICT = "timeframe_conflict"
    LOCATION_POOR = "location_poor"
    REWARD_RISK_INSUFFICIENT = "reward_risk_insufficient"
    VOLATILITY_ABNORMAL = "volatility_abnormal"
    DATA_UNSAFE = "data_unsafe"
    COOLDOWN_ACTIVE = "cooldown_active"
    DAILY_LOSS_LIMIT = "daily_loss_limit"
    DAILY_TRADE_LIMIT = "daily_trade_limit"
    INSUFFICIENT_INPUT = "insufficient_input"


@dataclass(frozen=True, slots=True)
class QualityContext:
    market_regime: MarketRegime
    location_score: Decimal | None
    reward_risk_ratio: Decimal | None
    volatility_ratio: Decimal | None
    data_fresh: bool
    cooldown_active: bool = False
    consecutive_losses: int = 0
    daily_loss_points: Decimal = ZERO
    daily_trade_count: int = 0


@dataclass(frozen=True, slots=True)
class QualityGateConfig:
    minimum_confidence: Decimal = Decimal(80)
    maximum_risk: Decimal = Decimal(30)
    minimum_location_score: Decimal = Decimal(70)
    minimum_reward_risk_ratio: Decimal = Decimal("1.5")
    minimum_volatility_ratio: Decimal = Decimal("0.60")
    maximum_volatility_ratio: Decimal = Decimal("1.80")
    maximum_consecutive_losses: int = 2
    maximum_daily_loss_points: Decimal = Decimal(40)
    maximum_daily_trades: int = 5

    def __post_init__(self) -> None:
        decimal_values = (
            self.minimum_confidence, self.maximum_risk, self.minimum_location_score,
            self.minimum_reward_risk_ratio, self.minimum_volatility_ratio,
            self.maximum_volatility_ratio, self.maximum_daily_loss_points,
        )
        if any(not value.is_finite() or value < ZERO for value in decimal_values):
            raise ValueError("Quality thresholds must be finite and non-negative.")
        if not ZERO <= self.minimum_confidence <= HUNDRED or not ZERO <= self.maximum_risk <= HUNDRED:
            raise ValueError("Confidence and risk thresholds must be within 0..100.")
        if self.minimum_volatility_ratio >= self.maximum_volatility_ratio:
            raise ValueError("Volatility range must be increasing.")
        if self.maximum_consecutive_losses <= 0 or self.maximum_daily_trades <= 0:
            raise ValueError("Loss and trade limits must be positive.")

    @classmethod
    def shadow_v1(cls) -> QualityGateConfig:
        return cls()


@dataclass(frozen=True, slots=True)
class QualityGateResult:
    engine_version: str
    evaluated_at: object
    decision: QualityDecision
    score: Decimal
    passed_conditions: int
    total_conditions: int
    supports: tuple[QualityReason, ...]
    blockers: tuple[QualityReason, ...]
    valid: bool
    live_order_allowed: bool = False


def evaluate_quality_gate(
    confidence: DecisionConfidenceResult,
    risk: RiskResult,
    context: QualityContext,
    config: QualityGateConfig,
) -> QualityGateResult:
    """Evaluate seven observable advantages and fail closed on any safety blocker."""
    if not isinstance(confidence, DecisionConfidenceResult) or not isinstance(risk, RiskResult):
        raise TypeError("confidence and risk must use supported result types")
    if confidence.evaluated_at != risk.evaluated_at:
        return QualityGateResult(QUALITY_GATE_VERSION, confidence.evaluated_at, QualityDecision.BLOCK, ZERO, 0, 7, (), (QualityReason.INSUFFICIENT_INPUT,), False)

    supports: list[QualityReason] = []
    blockers: list[QualityReason] = []
    checks = (
        (context.market_regime is MarketRegime.TREND, QualityReason.TREND_REGIME, QualityReason.REGIME_BLOCKED),
        (confidence.alignment_state in {TimeframeAlignmentState.FULLY_ALIGNED, TimeframeAlignmentState.MOSTLY_ALIGNED} and confidence.overall_confidence_score >= config.minimum_confidence, QualityReason.TIMEFRAMES_ALIGNED, QualityReason.TIMEFRAME_CONFLICT),
        (context.location_score is not None and context.location_score >= config.minimum_location_score, QualityReason.LOCATION_ACCEPTABLE, QualityReason.LOCATION_POOR),
        (context.reward_risk_ratio is not None and context.reward_risk_ratio >= config.minimum_reward_risk_ratio, QualityReason.REWARD_RISK_ACCEPTABLE, QualityReason.REWARD_RISK_INSUFFICIENT),
        (context.volatility_ratio is not None and config.minimum_volatility_ratio <= context.volatility_ratio <= config.maximum_volatility_ratio, QualityReason.VOLATILITY_ACCEPTABLE, QualityReason.VOLATILITY_ABNORMAL),
        (context.data_fresh and risk.operational_state is RiskOperationalState.VALID, QualityReason.DATA_FRESH, QualityReason.DATA_UNSAFE),
        (risk.overall_risk_score <= config.maximum_risk, QualityReason.RISK_ACCEPTABLE, QualityReason.DATA_UNSAFE),
    )
    for passed, support, blocker in checks:
        (supports if passed else blockers).append(support if passed else blocker)

    hard_blockers: list[QualityReason] = []
    if context.cooldown_active or context.consecutive_losses >= config.maximum_consecutive_losses:
        hard_blockers.append(QualityReason.COOLDOWN_ACTIVE)
    if context.daily_loss_points >= config.maximum_daily_loss_points:
        hard_blockers.append(QualityReason.DAILY_LOSS_LIMIT)
    if context.daily_trade_count >= config.maximum_daily_trades:
        hard_blockers.append(QualityReason.DAILY_TRADE_LIMIT)
    blockers.extend(hard_blockers)

    passed = len(supports)
    score = (Decimal(passed) / Decimal(len(checks)) * HUNDRED).quantize(Decimal(".01"), rounding=ROUND_HALF_UP)
    if hard_blockers or any(reason in blockers for reason in (QualityReason.REGIME_BLOCKED, QualityReason.TIMEFRAME_CONFLICT, QualityReason.DATA_UNSAFE)):
        decision = QualityDecision.BLOCK
    elif passed == len(checks):
        decision = QualityDecision.A_GRADE
    else:
        decision = QualityDecision.WAIT
    return QualityGateResult(QUALITY_GATE_VERSION, confidence.evaluated_at, decision, score, passed, len(checks), tuple(supports), tuple(dict.fromkeys(blockers)), True)
