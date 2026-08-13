"""Static HTML/CSS contract for the read-only KAM Trade V3 dashboard."""
from __future__ import annotations

from dataclasses import dataclass
from html import escape
from typing import Any, Mapping

DASHBOARD_UI_VERSION = "1.0"
SECTION_IDS = (
    "dashboard-status-banner", "dashboard-header", "dashboard-three-second-summary",
    "dashboard-market-decision", "dashboard-timeframes", "dashboard-modules",
    "dashboard-messages", "dashboard-footer",
)
DECISION_IDS = ("decision-direction", "decision-confidence", "decision-risk", "decision-next-step")
TIMEFRAME_IDS = ("timeframe-5m", "timeframe-15m", "timeframe-60m", "timeframe-1d", "timeframe-1w")
MODULE_IDS = ("module-position", "module-trend", "module-structure", "module-timing")
CSS_TOKENS = ("--page-bg", "--panel-bg", "--text-primary", "--text-secondary", "--border", "--focus", "--state-normal", "--state-waiting", "--state-caution", "--state-danger", "--state-unavailable")


@dataclass(frozen=True, slots=True)
class DashboardUIConfig:
    ui_version: str = DASHBOARD_UI_VERSION
    language: str = "zh-TW"
    include_development_metadata: bool = False

    def __post_init__(self) -> None:
        if self.ui_version != DASHBOARD_UI_VERSION or self.language != "zh-TW":
            raise ValueError("Invalid Dashboard UI configuration")

    @classmethod
    def provisional(cls) -> "DashboardUIConfig":
        return cls()


def _text(value: Any) -> str:
    """Presenter output is already escaped; escape again only for attributes."""
    return "—" if value is None or value == "" else str(value)


def _item(label: str, value: Any) -> str:
    return f'<div class="metric"><span>{escape(label)}</span><strong>{_text(value)}</strong></div>'


def _card(identifier: str, title: str, body: str, css_class: str = "") -> str:
    return f'<article id="{identifier}" class="ui-card {escape(css_class, quote=True)}"><h3>{escape(title)}</h3>{body}</article>'


def _progress(score: str) -> str:
    """Only expose a valid ARIA bar for a finite 0..100 display score."""
    try:
        value = float(score)
    except (TypeError, ValueError):
        return ""
    if not 0 <= value <= 100:
        return ""
    normalized = f"{value:g}"
    return f'<div class="progress" role="progressbar" aria-label="Confidence score" aria-valuemin="0" aria-valuemax="100" aria-valuenow="{normalized}"><span style="width:{normalized}%"></span></div>'


def render_dashboard_ui(template_context: Mapping[str, Any], config: DashboardUIConfig) -> str:
    """Render the fixed V3 DOM using only a Presenter template context.

    This function does not parse or calculate market values. It intentionally
    contains no client-side scripts, API calls, or account/trading controls.
    """
    if not isinstance(config, DashboardUIConfig) or not isinstance(template_context, Mapping):
        raise TypeError("A Dashboard UI config and presenter template context are required")
    required = {"header", "summary", "decision", "timeframe_cards", "module_sections", "message_banner", "messages", "footer", "accessibility", "theme_state"}
    if not required.issubset(template_context):
        raise ValueError("Incomplete presenter template context")
    header = template_context["header"]
    summary = template_context["summary"]
    decision = template_context["decision"]
    banner = template_context["message_banner"]
    accessibility = template_context["accessibility"]
    if not all(isinstance(x, Mapping) for x in (header, summary, decision, banner, accessibility)):
        raise ValueError("Invalid presenter template context")
    state_class = _text(header.get("badge_class"))
    banner_html = ""
    if banner.get("visible"):
        banner_html = f'<section id="dashboard-status-banner" class="status-banner {escape(_text(banner.get("state_class")), quote=True)}" role="status" aria-live="{escape(_text(banner.get("aria_live")), quote=True)}"><strong>{_text(banner.get("title"))}</strong><span>{_text(banner.get("short_text"))}</span></section>'
    else:
        banner_html = '<section id="dashboard-status-banner" class="status-banner" hidden aria-hidden="true"></section>'
    header_html = f'''<header id="dashboard-header" class="dashboard-header {escape(state_class, quote=True)}">
<div><p class="eyebrow">{_text(header.get("product_type"))}</p><h1>{_text(header.get("title"))}</h1><p>{_text(header.get("subtitle"))}</p></div>
<div class="header-state"><span class="badge {escape(state_class, quote=True)}">{_text(header.get("badge_text"))}</span><span>{_text(header.get("evaluated_at_text"))}</span></div></header>'''
    summary_html = f'''<section id="dashboard-three-second-summary" class="summary-hero {escape(_text(summary.get("state_class")), quote=True)}" aria-labelledby="summary-heading" aria-describedby="summary-detail">
<p class="eyebrow">Three-second summary</p><h2 id="summary-heading">{_text(summary.get("headline"))}</h2>
<div class="summary-chips"><span>{_text(summary.get("direction_text"))}</span><span>{_text(summary.get("confidence_text"))}</span><span>{_text(summary.get("risk_text"))}</span><span>{_text(summary.get("next_step_text"))}</span></div>
<p id="summary-detail">{_text(summary.get("attention_text"))} · {_text(header.get("evaluated_at_text"))}</p></section>'''
    confidence = _text(decision.get("confidence_score_text")); risk = _text(decision.get("risk_score_text"))
    decision_html = f'''<section id="dashboard-market-decision" aria-label="{escape(_text(accessibility.get("decision_aria_label")), quote=True)}"><h2>Market decision</h2><div class="decision-grid">
{_card("decision-direction", "Direction", _item("State", decision.get("direction_text")), _text(decision.get("direction_class")))}
{_card("decision-confidence", "Confidence", _item("Score", confidence) + _progress(confidence), _text(decision.get("confidence_class")))}
{_card("decision-risk", "Risk", _item("Score", risk) + _item("Level", decision.get("risk_text")), _text(decision.get("risk_class")))}
{_card("decision-next-step", "Next step", _item("Workflow", decision.get("next_step_text")) + _item("Priority", decision.get("priority_text")), _text(decision.get("next_step_class")))}
</div></section>'''
    frames = template_context["timeframe_cards"]
    invalid_page = _text(header.get("display_state")) == "invalid"
    if invalid_page and not frames:
        frames = tuple({"display_label": label, "state_class": "state-invalid", "direction_text": "—", "confidence_score_text": "—", "risk_score_text": "—", "next_step_text": "—"} for label in ("5m", "15m", "60m", "1d", "1w"))
    if not isinstance(frames, (tuple, list)) or len(frames) != 5:
        raise ValueError("The UI requires five timeframe cards")
    frame_html = []
    for card, identifier in zip(frames, TIMEFRAME_IDS, strict=True):
        if not isinstance(card, Mapping):
            raise ValueError("Invalid timeframe card")
        body = _item("Direction", card.get("direction_text")) + _item("Confidence", card.get("confidence_score_text")) + _item("Risk", card.get("risk_score_text")) + _item("Next", card.get("next_step_text"))
        frame_html.append(_card(identifier, _text(card.get("display_label")), body, _text(card.get("state_class"))))
    module_map: dict[str, Mapping[str, Any]] = {}
    for module in template_context["module_sections"]:
        if isinstance(module, Mapping) and module.get("module") not in module_map:
            module_map[str(module.get("module"))] = module
    if invalid_page and not module_map:
        module_map = {name: {"module": name, "title": name.title(), "question": "—", "headline": "—", "short_reason": "—", "state_class": "state-invalid"} for name in ("position", "trend", "structure", "timing")}
    if set(module_map) != set(MODULE_IDS[i].replace("module-", "") for i in range(4)):
        raise ValueError("The UI requires the four module sections")
    modules_html = []
    for identifier in MODULE_IDS:
        name = identifier.replace("module-", "")
        module = module_map[name]
        body = f'<p class="module-question">{_text(module.get("question"))}</p>' + _item("State", module.get("headline")) + _item("Reason", module.get("short_reason"))
        modules_html.append(_card(identifier, _text(module.get("title")), body, _text(module.get("state_class"))))
    messages = template_context["messages"]
    message_html = "".join(f"<li>{_text(message)}</li>" for message in messages) or "<li>—</li>"
    footer = template_context["footer"]
    metadata = f'<span>UI {DASHBOARD_UI_VERSION}</span><span>Presenter {_text(footer.get("presenter_version"))}</span><span>Adapter {_text(template_context.get("adapter_version"))}</span>'
    if config.include_development_metadata:
        metadata += f'<span>Source {_text(footer.get("source_version"))}</span><span>Serialization {_text(footer.get("serialization_version"))}</span>'
    return f'''<!doctype html><html lang="zh-TW"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>KAM Trade V3</title><link rel="stylesheet" href="/static/dashboard.css"></head>
<body class="theme-{escape(_text(template_context["theme_state"]), quote=True)}"><a class="skip-link" href="#dashboard-main">Skip to main content</a><main id="dashboard-main" aria-label="{escape(_text(accessibility.get("page_landmark_label")), quote=True)}">{banner_html}{header_html}{summary_html}{decision_html}<section id="dashboard-timeframes" aria-label="{escape(_text(accessibility.get("timeframe_group_label")), quote=True)}"><h2>Timeframes</h2><div class="timeframe-grid">{''.join(frame_html)}</div></section><section id="dashboard-modules" aria-label="{escape(_text(accessibility.get("module_group_label")), quote=True)}"><h2>Module detail</h2><div class="module-grid">{''.join(modules_html)}</div></section><section id="dashboard-messages" aria-label="{escape(_text(accessibility.get("message_region_label")), quote=True)}"><h2>Messages</h2><ul>{message_html}</ul></section><footer id="dashboard-footer"><span>KAM Trade V3 · Trading Decision Operating System</span>{metadata}</footer></main></body></html>'''
