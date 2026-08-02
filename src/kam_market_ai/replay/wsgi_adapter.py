"""WSGI-neutral, read-only context adapter for ReplayPresenterView."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Mapping
from .presenter import REPLAY_PRESENTER_VERSION, ReplayPresenterView
REPLAY_WSGI_ADAPTER_VERSION="1.0"; REPLAY_UI_VERSION="1.0"
@dataclass(frozen=True,slots=True)
class ReplayWSGIAdapterConfig:
 adapter_version:str=REPLAY_WSGI_ADAPTER_VERSION; supported_presenter_versions:frozenset[str]=frozenset({REPLAY_PRESENTER_VERSION}); content_type:str="text/html"; charset:str="utf-8"; cache_control:str="no-store"; default_http_status:int=200; invalid_market_http_status:int=200; internal_error_http_status:int=500; method_not_allowed_http_status:int=405; allow_fixture_preview:bool=False; fixture_whitelist:frozenset[str]=frozenset(); development_mode:bool=False; include_debug_metadata:bool=False; include_raw_hashes:bool=False; include_lineage:bool=False; maximum_context_size:int=262144; correlation_id_policy:str="none"; fail_closed_policy:str="page"
 def __post_init__(self):
  if self.adapter_version!=REPLAY_WSGI_ADAPTER_VERSION or self.content_type!="text/html" or self.charset!="utf-8" or self.cache_control!="no-store" or self.fail_closed_policy!="page": raise ValueError("Invalid Replay WSGI config")
@dataclass(frozen=True,slots=True)
class ReplayWSGIContext:
 adapter_version:str; presenter_version:str; ui_version:str; template_name:str; language:str; page_title:str; page_subtitle:str; section_order:tuple[str,...]; status_banner:Mapping[str,object]; header:Mapping[str,object]; hero:Mapping[str,object]; progress:Mapping[str,object]; decision:Mapping[str,object]; comparison:Mapping[str,object]; timeframe_cards:tuple[Mapping[str,object],...]; module_cards:tuple[Mapping[str,object],...]; messages:tuple[Mapping[str,object],...]; footer:Mapping[str,object]; accessibility:Mapping[str,object]; fixture_preview:bool; development_mode:bool; valid:bool; warnings:tuple[str,...]; error_codes:tuple[str,...]; http_status:int; response_headers:tuple[tuple[str,str],...]
def build_replay_wsgi_context(presenter:ReplayPresenterView,config:ReplayWSGIAdapterConfig)->ReplayWSGIContext:
 if not isinstance(config,ReplayWSGIAdapterConfig): raise TypeError("ReplayWSGIAdapterConfig required")
 if not isinstance(presenter,ReplayPresenterView) or presenter.presenter_version not in config.supported_presenter_versions: raise TypeError("supported ReplayPresenterView required")
 headers=(("Content-Type",f"{config.content_type}; charset={config.charset}"),("Cache-Control",config.cache_control))
 return ReplayWSGIContext(config.adapter_version,presenter.presenter_version,REPLAY_UI_VERSION,"replay_dashboard.html",presenter.accessibility["language"],presenter.page_title,presenter.page_subtitle,presenter.section_order,presenter.status_banner,presenter.header,presenter.hero,presenter.progress,presenter.decision,presenter.comparison_summary,presenter.timeframe_cards,presenter.module_cards,presenter.messages,presenter.footer,presenter.accessibility,config.development_mode,config.development_mode,presenter.valid,presenter.warnings,presenter.error_codes,config.default_http_status,headers)
