"""Composition helper for an explicitly supplied local Paper Trading view."""
from __future__ import annotations

from collections.abc import Callable

from .operator_presenter import PaperTradingOperatorView
from .operator_wsgi import build_operator_wsgi


def create_demo_operator_app():
    """Compose only fixed offline DEMO data; it has no external data source."""
    from .demo_proposal import build_demo_session
    from .demo_snapshot import DEMO_SNAPSHOT
    from .operator_presenter import build_demo_operator_presenter
    proposal, matching = build_demo_session()
    return build_operator_wsgi(lambda: build_demo_operator_presenter(proposal, matching, DEMO_SNAPSHOT))


def create_operator_app(view_provider: Callable[[], PaperTradingOperatorView]):
    """Return the GET-only WSGI app; no server is started here."""
    return build_operator_wsgi(view_provider)
