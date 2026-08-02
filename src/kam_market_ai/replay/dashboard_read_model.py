"""Read-only Replay dashboard model; it never invokes engines or decisions."""
from __future__ import annotations
from dataclasses import dataclass
from enum import StrEnum
from typing import Mapping
from .comparison import ReplayFrameComparison, compare_replay_frames
from .evaluation_contract import EvaluatedReplayFrame
from .input_contract import ReplayTimeframe

REPLAY_DASHBOARD_READ_MODEL_VERSION="1.0"
class ReplayDisplayState(StrEnum): READY="ready"; UNAVAILABLE="unavailable"; BLOCKED="blocked"; INVALID="invalid"; STALE="stale"
class ReplayAttentionLevel(StrEnum): NORMAL="normal"; NOTICE="notice"; WARNING="warning"; CRITICAL="critical"; UNAVAILABLE="unavailable"
@dataclass(frozen=True,slots=True)
class ReplayProgressView: current_index:int; current_sequence:int; total_frames:int; progress_ratio:float; progress_percent:int; is_first:bool; is_last:bool; previous_frame_id:str|None; next_frame_id:str|None; source_event_sequence:int; source_event_type:str
@dataclass(frozen=True,slots=True)
class ReplayHeroView: frame_label:str; replay_position:str; occurred_at:object; evaluated_at:object; direction:object; confidence:object; risk:object; next_step:object; display_state:ReplayDisplayState; attention_level:ReplayAttentionLevel; valid:bool; change_summary:tuple[str,...]; previous_available:bool; next_available:bool
@dataclass(frozen=True,slots=True)
class ReplayDecisionSummaryView: direction:object; direction_state:str; confidence:object; confidence_state:str; risk:object; risk_state:str; next_step:object; next_step_state:str; evaluated:bool; valid:bool; source_frame_id:str; source_evaluation_id:str; warnings:tuple[str,...]; error_codes:tuple[str,...]
@dataclass(frozen=True,slots=True)
class ReplayTimeframeCard: timeframe:ReplayTimeframe; update_state:object; candle_state:object; market_data_state:str|None; direction:object; confidence:object; risk:object; next_step:object; valid:bool; stale:bool; unavailable:bool; changed:bool; change_type:str; previous_state:object; current_state:object; source_snapshot_at:object; inherited:bool; warnings:tuple[str,...]; error_codes:tuple[str,...]
@dataclass(frozen=True,slots=True)
class ReplayModuleCard:
 module:str; current_state:str; previous_state:str|None; changed:bool; change_type:str; evaluated_slot_count:int; valid_slot_count:int; unavailable_slot_count:int; stale_slot_count:int; invalid_slot_count:int; attention_level:ReplayAttentionLevel; summary:str; warnings:tuple[str,...]; error_codes:tuple[str,...]
 @property
 def valid(self)->bool: return self.valid_slot_count==self.evaluated_slot_count
@dataclass(frozen=True,slots=True)
class ReplayDashboardReadModel: read_model_version:str; comparison_version:str; scenario_id:str; run_id:str; frame_id:str; frame_sequence:int; total_frames:int; previous_frame_id:str|None; next_frame_id:str|None; occurred_at:object; evaluated_at:object; timezone:str; symbol:str; market:str; session_state:object; replay_state:object; replay_progress:ReplayProgressView; frame_state:object; evaluation_state:object; display_state:ReplayDisplayState; attention_level:ReplayAttentionLevel; valid:bool; stale:bool; blocked:bool; unavailable:bool; hero:ReplayHeroView; decision_summary:ReplayDecisionSummaryView; timeframe_cards:tuple[ReplayTimeframeCard,...]; module_cards:tuple[ReplayModuleCard,...]; comparison:ReplayFrameComparison; messages:tuple[str,...]; version_info:Mapping[str,str]; source_lineage:Mapping[str,str]; warnings:tuple[str,...]; error_codes:tuple[str,...]
def build_replay_dashboard_read_model(current:EvaluatedReplayFrame,previous:EvaluatedReplayFrame|None=None,total_frames:int=1,next_frame_id:str|None=None)->ReplayDashboardReadModel:
 if not isinstance(current,EvaluatedReplayFrame): raise TypeError("current must be EvaluatedReplayFrame")
 if total_frames<=0: raise ValueError("total_frames must be positive")
 comparison=compare_replay_frames(previous,current); f=current.frame; decision=current.evaluation.decision_evaluation; available=bool(decision and decision.valid and current.valid and comparison.valid)
 blocked=f.frame_state.value in {"blocked","data_gap"}; stale=f.frame_state.value=="stale"; display=ReplayDisplayState.INVALID if not f.valid else ReplayDisplayState.BLOCKED if blocked else ReplayDisplayState.STALE if stale else ReplayDisplayState.READY if available else ReplayDisplayState.UNAVAILABLE; attention=ReplayAttentionLevel.CRITICAL if display is ReplayDisplayState.INVALID else ReplayAttentionLevel.WARNING if display in {ReplayDisplayState.BLOCKED,ReplayDisplayState.STALE} else ReplayAttentionLevel.NORMAL if available else ReplayAttentionLevel.UNAVAILABLE
 co=getattr(decision,"confidence",None) if available else None; ri=getattr(decision,"risk",None) if available else None; ns=getattr(decision,"next_step",None) if available else None
 direction=getattr(co,"overall_direction",None); confidence=getattr(co,"overall_confidence_score",None); risk=getattr(ri,"overall_risk_score",None); next_step=getattr(ns,"next_step",None)
 cards=[]
 for change in comparison.timeframe_changes:
  slot=f.timeframe_states.get(change.timeframe); cards.append(ReplayTimeframeCard(change.timeframe,getattr(slot,"update_state",None),getattr(slot,"candle_state",None),getattr(slot,"market_data_state",None),direction,confidence,risk,next_step,bool(slot and slot.valid),getattr(slot,"update_state",None)=="stale",slot is None,change.update_state_change.changed,change.update_state_change.change_type,change.update_state_change.previous,change.update_state_change.current,getattr(slot,"source_snapshot_at",None),bool(getattr(slot,"inherited_from_frame_id",None)),tuple(getattr(slot,"warnings",())),tuple(getattr(slot,"error_codes",()))))
 modules=tuple(ReplayModuleCard(m.module,"available" if available else "unavailable",None,m.change_type!="unchanged",m.change_type,4,4 if available else 0,0 if available else 4,0,0,attention,"frame-to-frame state comparison",(),()) for m in comparison.module_changes)
 changed=tuple(c.field for c in (comparison.direction_change,comparison.confidence_change,comparison.risk_change,comparison.next_step_change) if c.changed)
 messages=("initial_frame",) if comparison.comparison_state.value=="initial" else ("blocked",) if blocked else ("unavailable",) if not available else tuple(f"{x}_changed" for x in changed) or ("no_change",)
 progress=ReplayProgressView(f.frame_sequence-1,f.frame_sequence,total_frames,min(1,max(0,f.frame_sequence/total_frames)),round(min(1,max(0,f.frame_sequence/total_frames))*100),f.frame_sequence==1,f.frame_sequence==total_frames,f.previous_frame_id,next_frame_id,f.source_event_sequence,f.event_type.value)
 summary=ReplayDecisionSummaryView(direction,getattr(getattr(co,"overall_direction",None),"value","unavailable"),confidence,getattr(getattr(co,"overall_confidence_state",None),"value","unavailable"),risk,getattr(getattr(ri,"operational_state",None),"value","unavailable"),next_step,getattr(getattr(ns,"operational_state",None),"value","unavailable"),available,available,f.frame_id,current.evaluation.evaluation_id,tuple(getattr(decision,"warnings",())),tuple(getattr(decision,"error_codes",())))
 hero=ReplayHeroView(f"Frame {f.frame_sequence}",f"{f.frame_sequence}/{total_frames}",f.occurred_at,f.evaluated_at,direction,confidence,risk,next_step,display,attention,available,changed,previous is not None,next_frame_id is not None)
 return ReplayDashboardReadModel(REPLAY_DASHBOARD_READ_MODEL_VERSION,comparison.comparison_version,f.scenario_id,f.run_id,f.frame_id,f.frame_sequence,total_frames,f.previous_frame_id,next_frame_id,f.occurred_at,f.evaluated_at,f.timezone,f.symbol,f.market,f.session_state,f.frame_state,progress,f.frame_state,current.evaluation.evaluation_state,display,attention,available,stale,blocked,not available,hero,summary,tuple(cards),modules,comparison,messages,{"read_model":REPLAY_DASHBOARD_READ_MODEL_VERSION,"comparison":comparison.comparison_version},dict(f.source_lineage),tuple(f.warnings),tuple(f.error_codes))
