"""Canonical JSON serialization for Replay dashboard data only."""
from __future__ import annotations
from dataclasses import asdict,is_dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
import json
from typing import Any
from .comparison import ReplayFrameComparison
from .dashboard_read_model import ReplayDashboardReadModel
REPLAY_DASHBOARD_SERIALIZATION_VERSION="1.0"
def _value(v:Any)->Any:
 if isinstance(v,StrEnum): return v.value
 if isinstance(v,datetime): return v.isoformat()
 if isinstance(v,Decimal): return str(v)
 if is_dataclass(v): return {k:_value(x) for k,x in asdict(v).items()}
 if isinstance(v,dict): return {str(getattr(k,"value",k)):_value(x) for k,x in v.items()}
 if isinstance(v,(tuple,list)): return [_value(x) for x in v]
 return v
def serialize_replay_dashboard_read_model(value:ReplayDashboardReadModel)->dict[str,Any]:
 if not isinstance(value,ReplayDashboardReadModel): raise TypeError("ReplayDashboardReadModel required")
 return {"replay_dashboard_serialization_version":REPLAY_DASHBOARD_SERIALIZATION_VERSION,"payload_type":"ReplayDashboardReadModel",**_value(value)}
def serialize_replay_frame_comparison(value:ReplayFrameComparison)->dict[str,Any]:
 if not isinstance(value,ReplayFrameComparison): raise TypeError("ReplayFrameComparison required")
 return {"replay_dashboard_serialization_version":REPLAY_DASHBOARD_SERIALIZATION_VERSION,"payload_type":"ReplayFrameComparison",**_value(value)}
def replay_dashboard_to_canonical_json(payload:dict[str,Any],pretty:bool=False)->str: return json.dumps(payload,ensure_ascii=False,sort_keys=True,indent=2 if pretty else None,separators=None if pretty else (",",":"),allow_nan=False)
def replay_comparison_to_canonical_json(payload:dict[str,Any],pretty:bool=False)->str: return replay_dashboard_to_canonical_json(payload,pretty)
