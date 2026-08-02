"""Canonical JSON serialization for typed Replay Presenter views."""
from __future__ import annotations
from dataclasses import asdict,is_dataclass,dataclass
import json
from typing import Any
from .presenter import REPLAY_PRESENTER_VERSION, ReplayPresenterView
REPLAY_PRESENTER_SERIALIZATION_VERSION="1.0"
@dataclass(frozen=True,slots=True)
class ReplayPresenterSerializationConfig:
 supported_presenter_versions:frozenset[str]=frozenset({REPLAY_PRESENTER_VERSION}); serialization_version:str=REPLAY_PRESENTER_SERIALIZATION_VERSION; ensure_ascii:bool=False; sort_keys:bool=True; indent:int|None=None; separators:tuple[str,str]=(",",":"); trailing_newline:bool=False; reject_non_finite:bool=True; include_warnings:bool=True; include_error_codes:bool=True; include_accessibility:bool=True; include_footer_versions:bool=True; maximum_payload_size:int=262144
def _value(value:Any):
 if is_dataclass(value): return {k:_value(v) for k,v in asdict(value).items()}
 if isinstance(value,dict): return {str(getattr(k,"value",k)):_value(v) for k,v in value.items()}
 if isinstance(value,(tuple,list)): return [_value(v) for v in value]
 return getattr(value,"value",value)
def serialize_replay_presenter(presenter:ReplayPresenterView,config:ReplayPresenterSerializationConfig)->dict[str,Any]:
 if not isinstance(presenter,ReplayPresenterView) or not isinstance(config,ReplayPresenterSerializationConfig) or presenter.presenter_version not in config.supported_presenter_versions: raise TypeError("supported ReplayPresenterView required")
 payload={"replay_presenter_serialization_version":config.serialization_version,"payload_type":"ReplayPresenterView",**_value(presenter)}
 if not config.include_warnings: payload.pop("warnings",None)
 if not config.include_error_codes: payload.pop("error_codes",None)
 if not config.include_accessibility: payload.pop("accessibility",None)
 raw=replay_presenter_to_canonical_json(payload,config)
 if len(raw.encode())>config.maximum_payload_size: raise ValueError("presenter_payload_too_large")
 return payload
def replay_presenter_to_canonical_json(payload:dict[str,Any],config:ReplayPresenterSerializationConfig)->str:
 raw=json.dumps(payload,ensure_ascii=config.ensure_ascii,sort_keys=config.sort_keys,indent=config.indent,separators=None if config.indent else config.separators,allow_nan=not config.reject_non_finite)
 return raw+"\n" if config.trailing_newline else raw
