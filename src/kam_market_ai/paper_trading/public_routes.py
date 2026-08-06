"""Pure public read-only route dispatcher; WSGI wiring is deliberately deferred."""
from __future__ import annotations

from dataclasses import dataclass
from json import dumps


@dataclass(frozen=True, slots=True)
class PublicRouteResponse:
    status_code: int
    content_type: str
    body: str
    headers: tuple[tuple[str, str], ...] = ()


def build_health_response() -> PublicRouteResponse:
    return PublicRouteResponse(200, "application/json; charset=utf-8", dumps({"status": "ok", "service": "kam-market-ai", "mode": "read-only"}, separators=(",", ":")))


def build_ready_response() -> PublicRouteResponse:
    return PublicRouteResponse(200, "application/json; charset=utf-8", dumps({"status": "ready", "source_mode": "offline-demo"}, separators=(",", ":")))


def build_embed_response() -> PublicRouteResponse:
    return PublicRouteResponse(200, "text/plain; charset=utf-8", "Embed presenter not wired yet.")


def dispatch_public_route(method: str, path: str) -> PublicRouteResponse | None:
    if path not in {"/healthz", "/readyz", "/embed"}:
        return None
    if method != "GET":
        return PublicRouteResponse(405, "text/plain; charset=utf-8", "Method Not Allowed", (("Allow", "GET"),))
    return {"/healthz": build_health_response, "/readyz": build_ready_response, "/embed": build_embed_response}[path]()
