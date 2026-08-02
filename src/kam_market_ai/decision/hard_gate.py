"""Hard gates run before grading. Missing facts always yield WAIT."""
from dataclasses import dataclass
from ..models import Decision, DecisionState, Instrument, MarketContext, MarketRegime, SessionKind, SignalGrade

@dataclass(frozen=True, slots=True)
class GatePolicy:
    a_score: int = 4
    a_plus_score: int = 6

class HardGate:
    def __init__(self, policy: GatePolicy = GatePolicy()) -> None: self.policy=policy
    def evaluate(self, context: MarketContext) -> Decision:
        reasons: list[str]=[]
        if context.session is SessionKind.CLOSED: reasons.append("SESSION_CLOSED")
        if context.opening_price is None: reasons.append("OPENING_POSITION_MISSING")
        if context.ma20 is None: reasons.append("MA20_MISSING")
        if context.regime is MarketRegime.UNKNOWN: reasons.append("MARKET_REGIME_UNKNOWN")
        if context.instrument in {Instrument.TX,Instrument.MTX} and context.session is SessionKind.DAY and not context.taiex_background_available:
            reasons.append("TAIEX_BACKGROUND_MISSING")
        if context.session is SessionKind.NIGHT and not context.overseas_background_available:
            reasons.append("OVERSEAS_BACKGROUND_MISSING")
        required_false=[key for key,value in context.facts.items() if not value]
        reasons.extend(f"CONDITION_NOT_MET:{key}" for key in sorted(required_false))
        if reasons: return Decision(DecisionState.WAIT,SignalGrade.NONE,tuple(reasons),0)
        score=sum((context.opening_price is not None, context.ma20 is not None,
                   context.regime is not MarketRegime.UNKNOWN, context.taiex_background_available,
                   context.v_reversal_confirmed, bool(context.support_zones or context.resistance_zones)))
        grade=SignalGrade.A_PLUS if score >= self.policy.a_plus_score else SignalGrade.A if score >= self.policy.a_score else SignalGrade.NONE
        if grade is SignalGrade.NONE: return Decision(DecisionState.WAIT,grade,("GRADE_BELOW_A",),score)
        return Decision(DecisionState.ELIGIBLE,grade,(),score)

