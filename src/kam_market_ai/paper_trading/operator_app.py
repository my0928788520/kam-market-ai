"""Composition helper for an explicitly supplied local Paper Trading view."""
from __future__ import annotations

from collections.abc import Callable

from .operator_presenter import PaperTradingOperatorView
from .operator_wsgi import build_operator_wsgi


def create_demo_operator_app(market_data_source=None, chart_data_source=None):
    """Compose only fixed offline DEMO data; it has no external data source."""
    from .demo_proposal import build_demo_session
    from .demo_snapshot import DEMO_SNAPSHOT
    from .operator_presenter import build_demo_operator_presenter
    proposal, matching = build_demo_session()
    return build_operator_wsgi(lambda: build_demo_operator_presenter(proposal, matching, DEMO_SNAPSHOT), market_data_source=market_data_source, chart_data_source=chart_data_source) if market_data_source is not None else build_operator_wsgi(lambda: build_demo_operator_presenter(proposal, matching, DEMO_SNAPSHOT), chart_data_source=chart_data_source)


def create_kam_rule_demo_operator_app(market_data_source=None, chart_data_source=None):
    """Compose the fixed local KAM Rule Adapter demonstration without I/O."""
    from datetime import date
    from decimal import Decimal
    from hashlib import sha256
    from .demo_snapshot import DEMO_SNAPSHOT
    from .kam_rule_adapter import KamRuleAdapterInput, KamTimeframeState, build_kam_rule_proposal
    from .operator_presenter import build_demo_operator_presenter
    value = KamRuleAdapterInput("DEMO-TW", DEMO_SNAPSHOT.snapshot_time, date(2026, 8, 13), "FRESH", Decimal("100"), KamTimeframeState("AU"), KamTimeframeState("AU"), KamTimeframeState("AU"), KamTimeframeState("AU"), KamTimeframeState("AU"), "U3", Decimal("98"), Decimal("102"), Decimal("98"), Decimal("102"), Decimal("1"), "kam-rule-demo-v1", sha256(b"kam-rule-demo").hexdigest())
    _, proposal, _ = build_kam_rule_proposal(value)
    return build_operator_wsgi(lambda: build_demo_operator_presenter(proposal, None, DEMO_SNAPSHOT), market_data_source=market_data_source, chart_data_source=chart_data_source) if market_data_source is not None else build_operator_wsgi(lambda: build_demo_operator_presenter(proposal, None, DEMO_SNAPSHOT), chart_data_source=chart_data_source)


def create_operator_app(view_provider: Callable[[], PaperTradingOperatorView], market_data_source=None, chart_data_source=None):
    """Return the GET-only WSGI app; no server is started here."""
    return build_operator_wsgi(view_provider, market_data_source=market_data_source, chart_data_source=chart_data_source) if market_data_source is not None else build_operator_wsgi(view_provider, chart_data_source=chart_data_source)
