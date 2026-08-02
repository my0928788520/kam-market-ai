"""Offline, fail-closed Pivot structure engine for KAM Trade V3."""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from typing import Mapping, Sequence

from ..models import Candle
from .pivot_detector import PlateauPolicy, Pivot, PivotType, detect_confirmed_pivots
from .position_engine import ALL_TIMEFRAMES, DataStatus, PositionTimeframe


class SwingLabel(StrEnum): HH="HH"; HL="HL"; LH="LH"; LL="LL"; EQH="EQH"; EQL="EQL"; UNCLASSIFIED="unclassified"
class StructureBias(StrEnum): BULLISH="bullish"; BEARISH="bearish"; NEUTRAL="neutral"; AMBIGUOUS="ambiguous"; INSUFFICIENT_DATA="insufficient_data"; INVALID="invalid"
class SequenceState(StrEnum): BULLISH_CONTINUATION="bullish_continuation"; BEARISH_CONTINUATION="bearish_continuation"; BULLISH_TRANSITION="bullish_transition"; BEARISH_TRANSITION="bearish_transition"; RANGE_LIKE="range_like"; MIXED="mixed"; INSUFFICIENT_DATA="insufficient_data"; AMBIGUOUS="ambiguous"; INVALID="invalid"
class PatternType(StrEnum): W_BOTTOM="w_bottom"; M_TOP="m_top"; NONE="none"; AMBIGUOUS="ambiguous"
class PatternState(StrEnum): NONE="none"; CANDIDATE="candidate"; NECKLINE_TESTING="neckline_testing"; CONFIRMED="confirmed"; FAILED="failed"; AMBIGUOUS="ambiguous"; INSUFFICIENT_DATA="insufficient_data"; INVALID="invalid"
class NecklineRelation(StrEnum): ABOVE="above"; BELOW="below"; TOUCHING="touching"; BREAKOUT_UP="breakout_up"; BREAKDOWN_DOWN="breakdown_down"; TESTING="testing"; INSUFFICIENT_DATA="insufficient_data"; INVALID="invalid"
class StructureToleranceMode(StrEnum): FIXED_POINTS="fixed_points"; PERCENTAGE="percentage"
class StructureDuplicatePolicy(StrEnum): REJECT="reject"; KEEP_FIRST="keep_first"; KEEP_LAST="keep_last"

@dataclass(frozen=True, slots=True)
class CandidateScoreWeights:
    """Provisional, internal-only candidate quality weights; not decision confidence."""
    recency: Decimal=Decimal("1")
    leg_symmetry: Decimal=Decimal("1")
    similarity: Decimal=Decimal("1")
    height: Decimal=Decimal("1")
    pivot_confirmation: Decimal=Decimal("1")
    neckline_proximity: Decimal=Decimal("1")
    invalidation_status: Decimal=Decimal("1")
    def __post_init__(self) -> None:
        if any(not value.is_finite() or value < 0 for value in (self.recency,self.leg_symmetry,self.similarity,self.height,self.pivot_confirmation,self.neckline_proximity,self.invalidation_status)):
            raise ValueError("Candidate score weights must be finite and non-negative.")

@dataclass(frozen=True, slots=True)
class StructureEngineConfig:
    lookback_by_timeframe: Mapping[PositionTimeframe,int]; minimum_closed_candles_by_timeframe: Mapping[PositionTimeframe,int]; minimum_pivots_by_timeframe: Mapping[PositionTimeframe,int]
    swing_comparison_tolerance_by_timeframe: Mapping[PositionTimeframe,Decimal]; pattern_similarity_tolerance_by_timeframe: Mapping[PositionTimeframe,Decimal]; neckline_tolerance_by_timeframe: Mapping[PositionTimeframe,Decimal]; invalidation_tolerance_by_timeframe: Mapping[PositionTimeframe,Decimal]; minimum_pattern_height_by_timeframe: Mapping[PositionTimeframe,Decimal]
    minimum_leg_separation_bars_by_timeframe: Mapping[PositionTimeframe,int]; maximum_leg_separation_bars_by_timeframe: Mapping[PositionTimeframe,int]; confirmation_bars_by_timeframe: Mapping[PositionTimeframe,int]; maximum_candidate_age_bars_by_timeframe: Mapping[PositionTimeframe,int]; stale_after_by_timeframe: Mapping[PositionTimeframe,timedelta]
    swing_comparison_tolerance_mode: StructureToleranceMode=StructureToleranceMode.PERCENTAGE; pattern_similarity_tolerance_mode: StructureToleranceMode=StructureToleranceMode.PERCENTAGE; neckline_tolerance_mode: StructureToleranceMode=StructureToleranceMode.PERCENTAGE; invalidation_tolerance_mode: StructureToleranceMode=StructureToleranceMode.PERCENTAGE
    pivot_left_window: int=2; pivot_right_window: int=2; plateau_policy: PlateauPolicy=PlateauPolicy.REJECT_PLATEAU; allow_sort_input: bool=True; duplicate_timestamp_policy: StructureDuplicatePolicy=StructureDuplicatePolicy.REJECT; ambiguity_score_gap: Decimal=Decimal("0.10")
    candidate_score_weights: CandidateScoreWeights=field(default_factory=CandidateScoreWeights)
    def __post_init__(self) -> None:
        maps=(self.lookback_by_timeframe,self.minimum_closed_candles_by_timeframe,self.minimum_pivots_by_timeframe,self.swing_comparison_tolerance_by_timeframe,self.pattern_similarity_tolerance_by_timeframe,self.neckline_tolerance_by_timeframe,self.invalidation_tolerance_by_timeframe,self.minimum_pattern_height_by_timeframe,self.minimum_leg_separation_bars_by_timeframe,self.maximum_leg_separation_bars_by_timeframe,self.confirmation_bars_by_timeframe,self.maximum_candidate_age_bars_by_timeframe,self.stale_after_by_timeframe)
        if any(set(ALL_TIMEFRAMES).difference(values) for values in maps): raise ValueError("Structure config is missing one or more timeframes.")
        if self.pivot_left_window<=0 or self.pivot_right_window<=0: raise ValueError("Pivot windows must be positive.")
        for tf in ALL_TIMEFRAMES:
            ints=(self.lookback_by_timeframe[tf],self.minimum_closed_candles_by_timeframe[tf],self.minimum_pivots_by_timeframe[tf],self.minimum_leg_separation_bars_by_timeframe[tf],self.maximum_leg_separation_bars_by_timeframe[tf],self.confirmation_bars_by_timeframe[tf],self.maximum_candidate_age_bars_by_timeframe[tf])
            if any(not isinstance(x,int) or x<=0 for x in ints) or ints[1]>ints[0] or ints[4]<ints[3]: raise ValueError(f"Invalid integer config for {tf.value}.")
            decimals=(self.swing_comparison_tolerance_by_timeframe[tf],self.pattern_similarity_tolerance_by_timeframe[tf],self.neckline_tolerance_by_timeframe[tf],self.invalidation_tolerance_by_timeframe[tf],self.minimum_pattern_height_by_timeframe[tf])
            if any(not isinstance(x,Decimal) or not x.is_finite() or x<=0 for x in decimals): raise ValueError(f"Invalid tolerance config for {tf.value}.")
            if not isinstance(self.stale_after_by_timeframe[tf],timedelta) or self.stale_after_by_timeframe[tf]<=timedelta(0): raise ValueError(f"Invalid stale config for {tf.value}.")
        if not self.ambiguity_score_gap.is_finite() or self.ambiguity_score_gap<0: raise ValueError("ambiguity_score_gap must be finite and non-negative.")
    @classmethod
    def provisional(cls) -> "StructureEngineConfig":
        def m(a,b,c,d): return {PositionTimeframe.M15:a,PositionTimeframe.M60:b,PositionTimeframe.D1:c,PositionTimeframe.W1:d}
        return cls(m(96,72,90,78),m(48,36,45,39),m(5,5,5,5),m(Decimal("0.30"),Decimal("0.35"),Decimal("0.50"),Decimal("0.75")),m(Decimal("0.30"),Decimal("0.35"),Decimal("0.50"),Decimal("0.75")),m(Decimal("0.10"),Decimal("0.12"),Decimal("0.20"),Decimal("0.30")),m(Decimal("0.25"),Decimal("0.30"),Decimal("0.45"),Decimal("0.70")),m(Decimal("0.40"),Decimal("0.50"),Decimal("1.00"),Decimal("2.00")),m(3,3,3,2),m(32,24,30,20),m(2,2,2,1),m(24,18,15,10),m(timedelta(minutes=30),timedelta(hours=2),timedelta(days=2),timedelta(days=14)))

@dataclass(frozen=True, slots=True)
class SwingPoint:
    timeframe: PositionTimeframe; pivot: Pivot; swing_label: SwingLabel; compared_to_pivot: Pivot|None; price_difference: Decimal|None; price_difference_percent: Decimal|None; tolerance_used: Decimal|None; confirmed: bool; warnings: tuple[str,...]=()
@dataclass(frozen=True, slots=True)
class PatternResult:
    pattern_type: PatternType; state: PatternState; first: Pivot|None; middle: Pivot|None; second: Pivot|None; neckline_price: Decimal|None; neckline_timestamp: datetime|None; difference: Decimal|None; difference_percent: Decimal|None; rebound_or_pullback: Decimal|None; rebound_or_pullback_percent: Decimal|None; bars_separation: int|None; current_relation_to_neckline: NecklineRelation; confirmation_bars: int; invalidation_reason: str|None; valid: bool; confidence: Decimal|None; warnings: tuple[str,...]=()
@dataclass(frozen=True, slots=True)
class StructureResult:
    timeframe: PositionTimeframe; pivots: tuple[Pivot,...]; swing_points: tuple[SwingPoint,...]; latest_high_label: SwingLabel; latest_low_label: SwingLabel; sequence_state: SequenceState; structure_bias: StructureBias; active_pattern_type: PatternType; w_bottom: PatternResult; m_top: PatternResult; neckline: PatternResult|None; current_price: Decimal|None; evaluated_at: datetime; candle_count:int; pivot_count:int; data_status:DataStatus; stale:bool; valid:bool; warnings:tuple[str,...]

def _d(v:object)->Decimal|None:
    try: x=Decimal(str(v))
    except (InvalidOperation,ValueError,TypeError): return None
    return x if x.is_finite() else None
def _tol(value:Decimal, percent:Decimal, mode:StructureToleranceMode)->Decimal: return percent if mode is StructureToleranceMode.FIXED_POINTS else value*percent/Decimal("100")
def _none(kind:PatternType=PatternType.NONE,state:PatternState=PatternState.NONE,warnings:tuple[str,...]=())->PatternResult: return PatternResult(kind,state,None,None,None,None,None,None,None,None,None,None,NecklineRelation.INSUFFICIENT_DATA,0,None,False,None,warnings)

def _swings(tf:PositionTimeframe,pivots:Sequence[Pivot],cfg:StructureEngineConfig)->tuple[SwingPoint,...]:
    last={PivotType.HIGH:None,PivotType.LOW:None}; out=[]
    for p in sorted(pivots,key=lambda x:x.candle_index):
        prior=last[p.pivot_type]; label=SwingLabel.UNCLASSIFIED; diff=percent=tolerance=None
        if prior:
            diff=p.price-prior.price; tolerance=_tol(prior.price,cfg.swing_comparison_tolerance_by_timeframe[tf],cfg.swing_comparison_tolerance_mode); percent=diff/prior.price*Decimal("100")
            if abs(diff)<=tolerance: label=SwingLabel.EQH if p.pivot_type is PivotType.HIGH else SwingLabel.EQL
            elif p.pivot_type is PivotType.HIGH: label=SwingLabel.HH if diff>0 else SwingLabel.LH
            else: label=SwingLabel.HL if diff>0 else SwingLabel.LL
        out.append(SwingPoint(tf,p,label,prior,diff,percent,tolerance,True)); last[p.pivot_type]=p
    return tuple(out)

def _sequence(swings:Sequence[SwingPoint])->tuple[SequenceState,StructureBias,SwingLabel,SwingLabel]:
    highs=[x.swing_label for x in swings if x.pivot.pivot_type is PivotType.HIGH]; lows=[x.swing_label for x in swings if x.pivot.pivot_type is PivotType.LOW]
    latest_h=highs[-1] if highs else SwingLabel.UNCLASSIFIED; latest_l=lows[-1] if lows else SwingLabel.UNCLASSIFIED
    bull=any(x in (SwingLabel.HH,SwingLabel.HL) for x in (*highs,*lows)); bear=any(x in (SwingLabel.LH,SwingLabel.LL) for x in (*highs,*lows))
    if not swings: return SequenceState.INSUFFICIENT_DATA,StructureBias.INSUFFICIENT_DATA,latest_h,latest_l
    if latest_h is SwingLabel.EQH or latest_l is SwingLabel.EQL: return SequenceState.RANGE_LIKE,StructureBias.NEUTRAL,latest_h,latest_l
    if bull and bear: return SequenceState.MIXED,StructureBias.NEUTRAL,latest_h,latest_l
    if latest_h is SwingLabel.HH and latest_l is SwingLabel.HL: return SequenceState.BULLISH_CONTINUATION,StructureBias.BULLISH,latest_h,latest_l
    if latest_h is SwingLabel.LH and latest_l is SwingLabel.LL: return SequenceState.BEARISH_CONTINUATION,StructureBias.BEARISH,latest_h,latest_l
    return SequenceState.INSUFFICIENT_DATA,StructureBias.INSUFFICIENT_DATA,latest_h,latest_l

def _pattern(tf:PositionTimeframe,kind:PatternType,pivots:Sequence[Pivot],closed:Sequence[Candle],price:Decimal,eval_at:datetime,cfg:StructureEngineConfig)->list[PatternResult]:
    first_type=PivotType.LOW if kind is PatternType.W_BOTTOM else PivotType.HIGH; mid_type=PivotType.HIGH if kind is PatternType.W_BOTTOM else PivotType.LOW; out=[]
    for a in [p for p in pivots if p.pivot_type is first_type]:
      for b in [p for p in pivots if p.pivot_type is mid_type and a.candle_index < p.candle_index]:
       for c in [p for p in pivots if p.pivot_type is first_type and b.candle_index < p.candle_index]:
        bars=c.candle_index-a.candle_index; base=(a.price+c.price)/Decimal("2"); sim=abs(c.price-a.price); simtol=_tol(base,cfg.pattern_similarity_tolerance_by_timeframe[tf],cfg.pattern_similarity_tolerance_mode); invalidtol=_tol(a.price,cfg.invalidation_tolerance_by_timeframe[tf],cfg.invalidation_tolerance_mode)
        height=(b.price-max(a.price,c.price)) if kind is PatternType.W_BOTTOM else (min(a.price,c.price)-b.price); heightpct=height/base*Decimal("100"); state=PatternState.CANDIDATE; reason=None
        if bars<cfg.minimum_leg_separation_bars_by_timeframe[tf] or bars>cfg.maximum_leg_separation_bars_by_timeframe[tf] or heightpct<cfg.minimum_pattern_height_by_timeframe[tf]: continue
        invalid=(c.price<a.price-invalidtol) if kind is PatternType.W_BOTTOM else (c.price>a.price+invalidtol)
        age=len(closed)-1-c.candle_index
        if invalid: state=PatternState.FAILED; reason="second_extreme_exceeds_invalidation_tolerance"
        elif sim>simtol: continue
        elif age>cfg.maximum_candidate_age_bars_by_timeframe[tf]: state=PatternState.FAILED; reason="candidate_age_expired"
        necktol=_tol(b.price,cfg.neckline_tolerance_by_timeframe[tf],cfg.neckline_tolerance_mode); after=closed[c.candle_index+1:]; target=(lambda x:_d(x.close)>b.price+necktol) if kind is PatternType.W_BOTTOM else (lambda x:_d(x.close)<b.price-necktol); run=0; confirmed=False
        for candle in after:
            run=run+1 if target(candle) else 0
            confirmed=confirmed or run>=cfg.confirmation_bars_by_timeframe[tf]
        if state is PatternState.CANDIDATE and confirmed: state=PatternState.CONFIRMED
        elif state is PatternState.CANDIDATE and abs(price-b.price)<=necktol: state=PatternState.NECKLINE_TESTING
        relation=(NecklineRelation.BREAKOUT_UP if kind is PatternType.W_BOTTOM else NecklineRelation.BREAKDOWN_DOWN) if confirmed else NecklineRelation.TOUCHING if abs(price-b.price)<=necktol else NecklineRelation.ABOVE if price>b.price else NecklineRelation.BELOW
        weights=cfg.candidate_score_weights; first_leg=b.candle_index-a.candle_index; second_leg=c.candle_index-b.candle_index
        symmetry=Decimal("1")-abs(Decimal(first_leg-second_leg))/Decimal(max(first_leg,second_leg))
        similarity=max(Decimal("0"),Decimal("1")-sim/simtol)
        proximity=max(Decimal("0"),Decimal("1")-abs(price-b.price)/(necktol*Decimal("4")))
        score=(weights.recency/(Decimal("1")+Decimal(age))+weights.leg_symmetry*symmetry+weights.similarity*similarity+weights.height*heightpct+weights.pivot_confirmation*Decimal("1")+weights.neckline_proximity*proximity+weights.invalidation_status*(Decimal("0") if invalid else Decimal("1")))
        out.append(PatternResult(kind,state,a,b,c,b.price,b.timestamp,sim,sim/base*Decimal("100"),height,heightpct,bars,relation,cfg.confirmation_bars_by_timeframe[tf],reason,state not in (PatternState.FAILED,PatternState.INVALID),score if state is not PatternState.FAILED else None,()))
    return out

def _pick(candidates:list[PatternResult],cfg:StructureEngineConfig)->PatternResult:
    if not candidates:return _none()
    ordered=sorted(candidates,key=lambda x:x.confidence or Decimal("-1"),reverse=True)
    if len(ordered)>1 and (ordered[0].confidence or 0)-(ordered[1].confidence or 0)<=cfg.ambiguity_score_gap:return _none(ordered[0].pattern_type,PatternState.AMBIGUOUS,("candidate_score_ambiguous",))
    return ordered[0]

def evaluate_structure(timeframe:PositionTimeframe,candles:Sequence[Candle],current_price:object,evaluated_at:datetime,config:StructureEngineConfig,precomputed_pivots:Sequence[Pivot]|None=None)->StructureResult:
    price=_d(current_price)
    if price is None or price<=0:return _result_error(timeframe,evaluated_at,DataStatus.INVALID,("invalid_current_price",),len(candles),price)
    warnings=[]; prepared=list(candles)
    try:
      if any(not isinstance(c,Candle) or c.start>=c.end or any(x is None or x<=0 for x in (_d(c.open),_d(c.high),_d(c.low),_d(c.close))) or _d(c.high)<_d(c.low) or not _d(c.low)<=_d(c.close)<=_d(c.high) for c in prepared): return _result_error(timeframe,evaluated_at,DataStatus.INVALID,("invalid_candle",),len(candles),price)
      aware=lambda x:x.tzinfo is not None and x.utcoffset() is not None
      if any(aware(c.end)!=aware(evaluated_at) for c in prepared):return _result_error(timeframe,evaluated_at,DataStatus.INVALID,("mixed_or_incompatible_timezone",),len(candles),price)
      if any(prepared[i].end>prepared[i+1].end for i in range(len(prepared)-1)):
        if not config.allow_sort_input:return _result_error(timeframe,evaluated_at,DataStatus.INVALID,("candles_out_of_order",),len(candles),price)
        prepared.sort(key=lambda c:c.end);warnings.append("candles_sorted_by_end")
      if len({c.end for c in prepared})!=len(prepared):
        if config.duplicate_timestamp_policy is StructureDuplicatePolicy.REJECT:
          return _result_error(timeframe,evaluated_at,DataStatus.INVALID,("duplicate_candle_timestamp",),len(candles),price)
        retained={}
        for candle in prepared:
          if config.duplicate_timestamp_policy is StructureDuplicatePolicy.KEEP_FIRST:
            retained.setdefault(candle.end,candle)
          else:
            retained[candle.end]=candle
        prepared=list(retained.values()); warnings.append("duplicate_candle_timestamp_resolved")
      if any(prepared[i].start<prepared[i-1].end for i in range(1,len(prepared))):return _result_error(timeframe,evaluated_at,DataStatus.INVALID,("overlapping_candles",),len(candles),price)
      closed=[c for c in prepared if c.end<=evaluated_at]
    except TypeError:return _result_error(timeframe,evaluated_at,DataStatus.INVALID,("incompatible_candle_timestamp",),len(candles),price)
    if len(closed)<config.minimum_closed_candles_by_timeframe[timeframe]:return _result_error(timeframe,evaluated_at,DataStatus.INSUFFICIENT_DATA,(*warnings,"insufficient_closed_candles"),len(prepared),price)
    sample=closed[-config.lookback_by_timeframe[timeframe]:]; offset=len(closed)-len(sample)
    if precomputed_pivots is None:pivots=detect_confirmed_pivots(timeframe,sample,left_window=config.pivot_left_window,right_window=config.pivot_right_window,plateau_policy=config.plateau_policy,index_offset=offset)
    else:
      pivots=tuple(precomputed_pivots)
      if (any(p.timeframe is not timeframe or not p.confirmed or p.candle_index < 0 or p.candle_index >= len(closed) or p.timestamp != closed[p.candle_index].end or p.price != _d(closed[p.candle_index].high if p.pivot_type is PivotType.HIGH else closed[p.candle_index].low) for p in pivots)
          or list(pivots)!=sorted(pivots,key=lambda p:p.candle_index)):return _result_error(timeframe,evaluated_at,DataStatus.INVALID,(*warnings,"invalid_precomputed_pivots"),len(prepared),price)
    stale=evaluated_at-prepared[-1].end>config.stale_after_by_timeframe[timeframe]
    if len(pivots)<config.minimum_pivots_by_timeframe[timeframe]:return _result_base(timeframe,pivots,(),SequenceState.INSUFFICIENT_DATA,StructureBias.INSUFFICIENT_DATA,PatternType.NONE,_none(),_none(),price,evaluated_at,len(prepared),DataStatus.STALE if stale else DataStatus.INSUFFICIENT_DATA,stale,False,(*warnings,"insufficient_pivots"))
    swings=_swings(timeframe,pivots,config); seq,bias,lh,ll=_sequence(swings); w=_pick(_pattern(timeframe,PatternType.W_BOTTOM,pivots,closed,price,evaluated_at,config),config); m=_pick(_pattern(timeframe,PatternType.M_TOP,pivots,closed,price,evaluated_at,config),config)
    active=PatternType.NONE; valid=True
    if w.state is PatternState.AMBIGUOUS or m.state is PatternState.AMBIGUOUS or (w.valid and m.valid and abs((w.confidence or 0)-(m.confidence or 0))<=config.ambiguity_score_gap): active=PatternType.AMBIGUOUS;seq=SequenceState.AMBIGUOUS;bias=StructureBias.AMBIGUOUS;valid=False;warnings.append("structure_candidate_ambiguous")
    elif w.valid and w.state is not PatternState.NONE: active=PatternType.W_BOTTOM
    elif m.valid and m.state is not PatternState.NONE: active=PatternType.M_TOP
    if stale:valid=False;warnings.append("stale_market_data")
    neck=w if active is PatternType.W_BOTTOM else m if active is PatternType.M_TOP else None
    return _result_base(timeframe,pivots,swings,seq,bias,active,w,m,price,evaluated_at,len(prepared),DataStatus.STALE if stale else DataStatus.OK,stale,valid,tuple(warnings),lh,ll,neck)

def _result_base(tf,pivots,swings,seq,bias,active,w,m,price,at,count,status,stale,valid,warnings,lh=SwingLabel.UNCLASSIFIED,ll=SwingLabel.UNCLASSIFIED,neck=None): return StructureResult(tf,tuple(pivots),tuple(swings),lh,ll,seq,bias,active,w,m,neck,price,at,count,len(pivots),status,stale,valid,tuple(warnings))
def _result_error(tf,at,status,warnings,count,price): return _result_base(tf,(),(),SequenceState.INVALID if status is DataStatus.INVALID else SequenceState.INSUFFICIENT_DATA,StructureBias.INVALID if status is DataStatus.INVALID else StructureBias.INSUFFICIENT_DATA,PatternType.NONE,_none(),_none(),price,at,count,status,False,False,warnings)
def evaluate_all_structures(candles_by_timeframe:Mapping[PositionTimeframe,Sequence[Candle]],current_price:object|Mapping[PositionTimeframe,object],evaluated_at:datetime,config:StructureEngineConfig,precomputed_pivots_by_timeframe:Mapping[PositionTimeframe,Sequence[Pivot]]|None=None)->dict[PositionTimeframe,StructureResult]:
    out={}
    for tf in ALL_TIMEFRAMES:
      candles=candles_by_timeframe.get(tf,());price=current_price.get(tf) if isinstance(current_price,Mapping) else current_price
      try:out[tf]=evaluate_structure(tf,candles,price,evaluated_at,config,(precomputed_pivots_by_timeframe or {}).get(tf))
      except Exception as e:out[tf]=_result_error(tf,evaluated_at,DataStatus.CALCULATION_ERROR,(f"unexpected_calculation_error:{type(e).__name__}",),len(candles),None)
    return out
