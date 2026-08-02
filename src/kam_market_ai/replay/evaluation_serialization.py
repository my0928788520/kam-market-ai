"""Canonical serialization for evaluated replay frame wrappers."""
from __future__ import annotations
from dataclasses import asdict, is_dataclass
from datetime import datetime
from enum import StrEnum
import json
from typing import Any
from .evaluation_contract import EvaluatedReplayFrame, ReplayEvaluationResult

REPLAY_EVALUATION_SERIALIZATION_VERSION="1.0"
def _value(value:Any)->Any:
    if isinstance(value,StrEnum): return value.value
    if isinstance(value,datetime): return value.isoformat()
    if is_dataclass(value): return {key:_value(item) for key,item in asdict(value).items()}
    if isinstance(value,dict): return {str(getattr(key,"value",key)):_value(item) for key,item in value.items()}
    if isinstance(value,(tuple,list)): return [_value(item) for item in value]
    if value is None or isinstance(value,(str,int,float,bool)): return value
    return str(value)
def serialize_replay_evaluation(value:ReplayEvaluationResult|EvaluatedReplayFrame)->dict[str,Any]:
    if not isinstance(value,(ReplayEvaluationResult,EvaluatedReplayFrame)): raise TypeError("evaluation contract required")
    return {"replay_evaluation_serialization_version":REPLAY_EVALUATION_SERIALIZATION_VERSION,"payload_type":type(value).__name__,**_value(value)}
def replay_evaluation_to_canonical_json(payload:dict[str,Any])->str: return json.dumps(payload,ensure_ascii=False,sort_keys=True,separators=(",",":"),allow_nan=False)
