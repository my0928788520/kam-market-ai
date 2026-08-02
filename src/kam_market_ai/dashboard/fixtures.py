"""Portable, deterministic dashboard fixture envelope helpers."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any
from .read_model import DashboardReadModel
from .serialization import DASHBOARD_SERIALIZATION_VERSION,DashboardSerializationConfig,serialize_dashboard_read_model
DASHBOARD_FIXTURE_VERSION="1.0"
@dataclass(frozen=True,slots=True)
class DashboardFixtureMetadata: fixture_version:str; name:str; scenario:str; description:str; created_for:str; read_model_version:str; serialization_version:str; evaluated_at:str; expected_display_state:str; expected_attention_level:str; expected_primary_reason:str|None; tags:tuple[str,...]
@dataclass(frozen=True,slots=True)
class DashboardFixture: metadata:DashboardFixtureMetadata; payload:dict[str,Any]; assertions:dict[str,Any]
def build_dashboard_fixture(name:str,model:DashboardReadModel,metadata:DashboardFixtureMetadata,config:DashboardSerializationConfig)->DashboardFixture:
 if metadata.fixture_version!=DASHBOARD_FIXTURE_VERSION or metadata.read_model_version!=model.version or metadata.serialization_version!=DASHBOARD_SERIALIZATION_VERSION:raise ValueError("Fixture metadata version mismatch")
 payload=serialize_dashboard_read_model(model,config);return DashboardFixture(metadata,payload,{"expected_valid":model.valid,"expected_direction":model.market_decision.direction,"expected_risk_level":model.market_decision.risk_level,"expected_next_step":model.market_decision.next_step,"expected_timeframe_count":4,"forbidden_terms":[]})
def validate_dashboard_fixture(fixture:DashboardFixture)->None:
 if fixture.metadata.fixture_version!=DASHBOARD_FIXTURE_VERSION or fixture.payload.get("serialization_version")!=DASHBOARD_SERIALIZATION_VERSION or len(fixture.payload.get("timeframe_views",[]))!=4:raise ValueError("Invalid Dashboard fixture")
