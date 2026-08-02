"""WSGI-neutral template context adapter for DashboardPresenterView 1.0."""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any, Mapping

from .presenter import DASHBOARD_PRESENTER_VERSION, DashboardPresenterView

DASHBOARD_WSGI_ADAPTER_VERSION = "1.0"
DEFAULT_FIXTURE_WHITELIST = frozenset({"bullish_aligned", "bearish_aligned", "wait_for_close", "higher_timeframe_conflict", "stale", "invalid", "market_closed", "high_confidence_high_risk", "partial_timeframe"})


@dataclass(frozen=True, slots=True)
class DashboardWSGIAdapterConfig:
    adapter_version: str = DASHBOARD_WSGI_ADAPTER_VERSION
    content_type: str = "text/html"
    charset: str = "utf-8"
    cache_control: str = "no-store"
    default_http_status: int = 200
    invalid_page_http_status: int = 200
    internal_error_http_status: int = 500
    allow_fixture_preview: bool = False
    fixture_whitelist: frozenset[str] = DEFAULT_FIXTURE_WHITELIST
    development_mode: bool = False
    include_debug_metadata: bool = False
    correlation_id_policy: str = "none"

    def __post_init__(self) -> None:
        if (self.adapter_version != DASHBOARD_WSGI_ADAPTER_VERSION or self.content_type != "text/html" or self.charset.lower() != "utf-8" or self.cache_control != "no-store" or self.default_http_status != 200 or self.invalid_page_http_status != 200 or self.internal_error_http_status != 500 or self.correlation_id_policy not in {"none", "provided"} or not self.fixture_whitelist):
            raise ValueError("Invalid Dashboard WSGI adapter configuration")

    @classmethod
    def provisional(cls) -> "DashboardWSGIAdapterConfig":
        return cls()


def build_dashboard_wsgi_context(presenter: DashboardPresenterView, config: DashboardWSGIAdapterConfig) -> Mapping[str, Any]:
    """Prepare an existing template route context without invoking any engine.

    Market states, including stale, blocked and invalid source data, are always
    successful HTTP dashboard responses.  Route and server errors remain the
    responsibility of the existing WSGI application.
    """
    if not isinstance(config, DashboardWSGIAdapterConfig):
        raise TypeError("config must be DashboardWSGIAdapterConfig")
    if not isinstance(presenter, DashboardPresenterView):
        return {"http_status": config.internal_error_http_status, "headers": (("Content-Type", f"{config.content_type}; charset={config.charset}"), ("Cache-Control", config.cache_control)), "template_context": {}, "valid": False}
    return {"http_status": config.default_http_status, "headers": (("Content-Type", f"{config.content_type}; charset={config.charset}"), ("Cache-Control", config.cache_control)), "template_context": presenter.template_context, "valid": presenter.valid, "adapter_version": config.adapter_version}


def load_fixture_preview(name: str, fixture_directory: Path, config: DashboardWSGIAdapterConfig) -> Mapping[str, Any]:
    """Load one fixed development fixture without resolving arbitrary paths."""
    if not config.development_mode or not config.allow_fixture_preview:
        raise PermissionError("Fixture preview is disabled")
    if name not in config.fixture_whitelist or "/" in name or "\\" in name or ".." in name:
        raise ValueError("Fixture name is not allowed")
    path = Path(fixture_directory) / f"{name}.json"
    if not path.is_file():
        raise FileNotFoundError("Fixture is unavailable")
    with path.open("r", encoding="utf-8") as stream:
        value = json.load(stream)
    if not isinstance(value, Mapping):
        raise ValueError("Fixture must be an object")
    return value
