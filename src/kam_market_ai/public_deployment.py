"""Immutable public read-only deployment contracts; no HTTP server integration."""
from __future__ import annotations
from dataclasses import dataclass
from enum import StrEnum
from urllib.parse import urlparse

class DeploymentMode(StrEnum):
    READ_ONLY = "read-only"
    PUBLIC_EMBED = "public-embed"

class AllowedFrameAncestorsValidator:
    @staticmethod
    def validate(values: tuple[str, ...]) -> tuple[str, ...]:
        if not values: raise ValueError("At least self must be explicit.")
        for value in values:
            if value == "'self'": continue
            parsed = urlparse(value)
            if value == "*" or parsed.scheme != "https" or not parsed.netloc or parsed.path not in ("", "/") or parsed.query or parsed.fragment or parsed.hostname in {"localhost", "127.0.0.1"}:
                raise ValueError("Invalid allowed frame ancestor.")
        return values

@dataclass(frozen=True, slots=True)
class PublicEmbedConfig:
    allowed_frame_ancestors: tuple[str, ...] = ("'self'",)
    public_base_url: str | None = None
    environment_label: str = "public-read-only"
    enable_embed: bool = True
    enable_account_drawer: bool = True
    deployment_mode: DeploymentMode = DeploymentMode.READ_ONLY
    def __post_init__(self) -> None: AllowedFrameAncestorsValidator.validate(self.allowed_frame_ancestors)
    @property
    def content_security_policy(self) -> str:
        return "default-src 'self'; frame-ancestors " + " ".join(self.allowed_frame_ancestors) + "; base-uri 'self'; form-action 'none'"

@dataclass(frozen=True, slots=True)
class EmbedRouteConfig:
    path: str = "/embed"
    default_instrument: str = "TMF"
    allowed_instruments: tuple[str, ...] = ("TX", "MTX", "TMF")
    def __post_init__(self) -> None:
        if self.path != "/embed" or self.default_instrument not in self.allowed_instruments: raise ValueError("Invalid embed route.")

@dataclass(frozen=True, slots=True)
class HealthCheckProvider:
    def payload(self) -> dict[str, str]: return {"status":"ok","service":"kam-market-ai","mode":"read-only"}

@dataclass(frozen=True, slots=True)
class ReadinessProvider:
    def payload(self) -> dict[str, str]: return {"status":"ready","service":"kam-market-ai","mode":"read-only"}
