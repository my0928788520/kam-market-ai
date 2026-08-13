"""Deterministic JSON-safe serialization for DashboardReadModel 1.0."""
from __future__ import annotations
from dataclasses import asdict, dataclass, is_dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
import json
from typing import Any
from .read_model import DASHBOARD_READ_MODEL_VERSION, DashboardReadModel
DASHBOARD_SERIALIZATION_VERSION="1.0"
@dataclass(frozen=True,slots=True)
class DashboardSerializationConfig:
 supported_read_model_versions:frozenset[str]=frozenset({DASHBOARD_READ_MODEL_VERSION}); decimal_mode:str="string"; ensure_ascii:bool=False; sort_keys:bool=False; indent:int|None=None; separators:tuple[str,str]=(",",":"); trailing_newline:bool=False; include_raw_state:bool=True; include_source_lineage:bool=True; include_warnings:bool=True; warning_limit:int=32; reject_non_finite:bool=True; reject_unknown_enum:bool=True
 def __post_init__(self):
  if self.decimal_mode not in {"string","integer_if_exact","number"} or self.warning_limit<=0:raise ValueError("Unsupported serialization configuration.")
 @classmethod
 def provisional(cls)->"DashboardSerializationConfig":return cls()
def _value(v:Any,c:DashboardSerializationConfig)->Any:
 if isinstance(v,StrEnum):return v.value
 if isinstance(v,Decimal):
  if not v.is_finite() and c.reject_non_finite:raise ValueError("Non-finite Decimal")
  if c.decimal_mode=="string":return str(v)
  if c.decimal_mode=="integer_if_exact":return int(v) if v==v.to_integral_value() else str(v)
  return int(v) if v==v.to_integral_value() else float(v)
 if isinstance(v,datetime):
  if v.tzinfo is None or v.utcoffset() is None:raise ValueError("Naive datetime")
  return v.isoformat()
 if is_dataclass(v):return {k:_value(x,c) for k,x in asdict(v).items()}
 if isinstance(v,dict):return {str(k.value if isinstance(k,StrEnum) else k):_value(x,c) for k,x in v.items()}
 if isinstance(v,(tuple,list)):return [_value(x,c) for x in v]
 if v is None or isinstance(v,(str,int,float,bool)):return v
 raise TypeError(f"Unsupported payload value: {type(v).__name__}")
def serialize_dashboard_read_model(model:DashboardReadModel,config:DashboardSerializationConfig)->dict[str,Any]:
 if not isinstance(model,DashboardReadModel) or model.version not in config.supported_read_model_versions:raise ValueError("Unsupported Dashboard Read Model")
 payload=_value(model,config); frames=payload.pop("timeframes"); payload["timeframe_views"]=[frames[key] for key in ("5m","15m","60m","1d","1w")]
 payload={"serialization_version":DASHBOARD_SERIALIZATION_VERSION,"read_model_version":model.version,"generated_from":"dashboard_read_model",**payload}
 return payload
def dashboard_payload_to_canonical_json(payload:dict[str,Any],config:DashboardSerializationConfig)->str:
 text=json.dumps(payload,ensure_ascii=config.ensure_ascii,sort_keys=config.sort_keys,indent=config.indent,separators=config.separators,allow_nan=False)
 return text+("\n" if config.trailing_newline else "")
