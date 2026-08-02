"""Deterministic, read-only comparisons between evaluated Replay frames."""
from __future__ import annotations
from dataclasses import asdict, dataclass, is_dataclass
from enum import StrEnum
from hashlib import sha256
import json
from typing import Mapping
from .evaluation_contract import EvaluatedReplayFrame
from .input_contract import ReplayTimeframe

REPLAY_FRAME_COMPARISON_VERSION = "1.0"
_TFS=(ReplayTimeframe.M15,ReplayTimeframe.M60,ReplayTimeframe.D1,ReplayTimeframe.W1); _MODULES=("position","trend","structure","timing")
class ReplayComparisonState(StrEnum): INITIAL="initial"; UNCHANGED="unchanged"; CHANGED="changed"; PARTIALLY_CHANGED="partially_changed"; UNAVAILABLE="unavailable"; INVALID="invalid"; BLOCKED="blocked"
@dataclass(frozen=True,slots=True)
class ReplayScalarChange: field:str; previous:object; current:object; changed:bool; change_type:str; delta:object|None; direction:str|None; previous_available:bool; current_available:bool; valid:bool
@dataclass(frozen=True,slots=True)
class ReplayCategoricalChange: field:str; previous:object; current:object; changed:bool; change_type:str; previous_available:bool; current_available:bool; valid:bool
@dataclass(frozen=True,slots=True)
class ReplayTimeframeComparison: timeframe:ReplayTimeframe; previous_available:bool; current_available:bool; update_state_change:ReplayCategoricalChange; candle_state_change:ReplayCategoricalChange; market_data_state_change:ReplayCategoricalChange; direction_change:ReplayCategoricalChange; confidence_change:ReplayScalarChange; risk_change:ReplayScalarChange; next_step_change:ReplayCategoricalChange; inherited_change:ReplayCategoricalChange; valid:bool; warnings:tuple[str,...]; error_codes:tuple[str,...]
@dataclass(frozen=True,slots=True)
class ReplayModuleComparison: module:str; previous_available:bool; current_available:bool; changed_timeframes:tuple[ReplayTimeframe,...]; unchanged_timeframes:tuple[ReplayTimeframe,...]; invalid_timeframes:tuple[ReplayTimeframe,...]; unavailable_timeframes:tuple[ReplayTimeframe,...]; stale_timeframes:tuple[ReplayTimeframe,...]; change_type:str; valid:bool; warnings:tuple[str,...]; error_codes:tuple[str,...]
@dataclass(frozen=True,slots=True)
class ReplayFrameComparison: comparison_version:str; scenario_id:str; previous_frame_id:str|None; current_frame_id:str; previous_frame_hash:str|None; current_frame_hash:str; comparison_id:str; comparison_state:ReplayComparisonState; previous_available:bool; direction_change:ReplayCategoricalChange; confidence_change:ReplayScalarChange; risk_change:ReplayScalarChange; next_step_change:ReplayCategoricalChange; timeframe_changes:tuple[ReplayTimeframeComparison,...]; module_changes:tuple[ReplayModuleComparison,...]; attention_change:ReplayCategoricalChange; validity_change:ReplayCategoricalChange; stale_change:ReplayCategoricalChange; blocked_change:ReplayCategoricalChange; changed_fields:tuple[str,...]; change_count:int; comparison_hash:str; valid:bool; warnings:tuple[str,...]; error_codes:tuple[str,...]; lineage:Mapping[str,str]
def _clean(v):
 if is_dataclass(v): return _clean(asdict(v))
 if isinstance(v,Mapping): return {str(getattr(k,"value",k)):_clean(x) for k,x in sorted(v.items(),key=lambda x:str(x[0]))}
 if isinstance(v,(tuple,list)): return [_clean(x) for x in v]
 return getattr(v,"value",v)
def _hash(v): return sha256(json.dumps(_clean(v),sort_keys=True,default=str,separators=(",",":"),ensure_ascii=False).encode()).hexdigest()
def _cat(field,p,c,initial=False):
 pa=p is not None; ca=c is not None; typ="initial" if initial else "became_available" if not pa and ca else "became_unavailable" if pa and not ca else "unchanged" if p==c else "changed"
 return ReplayCategoricalChange(field,p,c,p!=c,typ,pa,ca,True)
def _scalar(field,p,c,initial=False):
 pa=isinstance(p,(int,float)); ca=isinstance(c,(int,float)); delta=(c-p) if pa and ca else None; typ="initial" if initial else "became_available" if not pa and ca else "became_unavailable" if pa and not ca else "unchanged" if p==c else "increased" if delta is not None and delta>0 else "decreased" if delta is not None and delta<0 else "changed"
 return ReplayScalarChange(field,p,c,p!=c,typ,delta,"up" if delta and delta>0 else "down" if delta and delta<0 else None,pa,ca,True)
def _decision(value):
 d=value.evaluation.decision_evaluation
 return (getattr(getattr(d,"confidence",None),"overall_direction",None),getattr(getattr(d,"confidence",None),"overall_confidence_score",None),getattr(getattr(d,"risk",None),"overall_risk_score",None),getattr(getattr(d,"next_step",None),"next_step",None)) if d and d.valid else (None,None,None,None)
def compare_replay_frames(previous:EvaluatedReplayFrame|None,current:EvaluatedReplayFrame)->ReplayFrameComparison:
 if not isinstance(current,EvaluatedReplayFrame): raise TypeError("current must be EvaluatedReplayFrame")
 f=current.frame; initial=previous is None
 if previous is not None and not isinstance(previous,EvaluatedReplayFrame): raise TypeError("previous must be EvaluatedReplayFrame")
 errors=[]
 if not f.valid: errors.append("invalid_current_frame")
 if f.frame_state.value in {"blocked","data_gap"}: errors.append("blocked_current_frame")
 if previous and (previous.frame.scenario_id!=f.scenario_id or previous.frame.run_id!=f.run_id or previous.frame.frame_sequence>=f.frame_sequence): errors.append("invalid_comparison_source")
 a=_decision(previous) if previous else (None,)*4; b=_decision(current)
 changes=(_cat("direction",a[0],b[0],initial),_scalar("confidence",a[1],b[1],initial),_scalar("risk",a[2],b[2],initial),_cat("next_step",a[3],b[3],initial))
 tf=[]
 for key in _TFS:
  p=previous.frame.timeframe_states.get(key) if previous else None; c=f.timeframe_states.get(key)
  if c is None: errors.append("missing_timeframe")
  tf.append(ReplayTimeframeComparison(key,p is not None,c is not None,_cat("update_state",getattr(p,"update_state",None),getattr(c,"update_state",None),initial),_cat("candle_state",getattr(p,"candle_state",None),getattr(c,"candle_state",None),initial),_cat("market_data_state",getattr(p,"market_data_state",None),getattr(c,"market_data_state",None),initial),changes[0],changes[1],changes[2],changes[3],_cat("inherited",getattr(p,"inherited_from_frame_id",None),getattr(c,"inherited_from_frame_id",None),initial),c is not None,(),() if c else ("missing_timeframe",)))
 mods=[]
 for module in _MODULES:
  changed=tuple(x.timeframe for x in tf if x.update_state_change.changed); unchanged=tuple(x.timeframe for x in tf if not x.update_state_change.changed); unavailable=tuple(x.timeframe for x in tf if not x.current_available); stale=tuple(x.timeframe for x in tf if x.update_state_change.current=="stale")
  mods.append(ReplayModuleComparison(module,not initial,True,changed,unchanged,(),unavailable,stale,"initial" if initial else "changed" if changed else "unchanged",not unavailable,(),()))
 state=ReplayComparisonState.INVALID if errors and "invalid_current_frame" in errors else ReplayComparisonState.BLOCKED if "blocked_current_frame" in errors else ReplayComparisonState.INITIAL if initial else ReplayComparisonState.UNAVAILABLE if b[0] is None else ReplayComparisonState.CHANGED if any(x.changed for x in changes) else ReplayComparisonState.PARTIALLY_CHANGED if any(x.update_state_change.changed for x in tf) else ReplayComparisonState.UNCHANGED
 changed_fields=tuple(x.field for x in changes if x.changed)+tuple(f"timeframe:{x.timeframe.value}" for x in tf if x.update_state_change.changed)
 ident=_hash((f.scenario_id,getattr(previous.frame,"frame_id",None) if previous else None,f.frame_id,getattr(previous.frame,"frame_hash",None) if previous else None,f.frame_hash))
 base=(REPLAY_FRAME_COMPARISON_VERSION,f.scenario_id,getattr(previous.frame,"frame_id",None) if previous else None,f.frame_id,getattr(previous.frame,"frame_hash",None) if previous else None,f.frame_hash,ident,state,not initial,*changes,tuple(tf),tuple(mods),_cat("attention",None,None,initial),_cat("valid",getattr(previous,"valid",None),current.valid,initial),_cat("stale",getattr(previous.frame,"frame_state",None) if previous else None,f.frame_state,initial),_cat("blocked",getattr(previous.frame,"frame_state",None) if previous else None,f.frame_state,initial),changed_fields,len(changed_fields),not errors,(),tuple(errors),{"current_frame_hash":f.frame_hash})
 return ReplayFrameComparison(*base[:22],_hash(base),*base[22:])
