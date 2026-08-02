"""Deterministic, read-only presenter contract for KAM Trade V3 dashboards.

The presenter deliberately has no market-data, account, or decision-engine
dependencies.  It converts the two supported canonical dashboard inputs into
template-safe display values only.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from html import escape
from typing import Any, Mapping

from .read_model import DASHBOARD_READ_MODEL_VERSION, DashboardReadModel
from .serialization import DASHBOARD_SERIALIZATION_VERSION, DashboardSerializationConfig, serialize_dashboard_read_model

DASHBOARD_PRESENTER_VERSION = "1.0"


class DashboardThemeState(StrEnum):
    NORMAL = "normal"
    CALM = "calm"
    WAITING = "waiting"
    CAUTION = "caution"
    DANGER = "danger"
    UNAVAILABLE = "unavailable"


class DashboardSectionKey(StrEnum):
    HEADER = "header"
    MARKET_OVERVIEW = "market_overview"
    THREE_SECOND_SUMMARY = "three_second_summary"
    MARKET_DECISION = "market_decision"
    TIMEFRAME_CARDS = "timeframe_cards"
    MODULE_DETAILS = "module_details"
    MESSAGES = "messages"
    FOOTER = "footer"


_TIMEFRAMES = ("15m", "60m", "1d", "1w")
_MODULES = ("position", "trend", "structure", "timing")
_DISPLAY_CLASSES = {
    "ready": "state-ready", "observing": "state-observing", "waiting": "state-waiting",
    "review_required": "state-review", "blocked": "state-blocked", "market_closed": "state-closed",
    "stale": "state-stale", "insufficient": "state-insufficient", "unavailable": "state-insufficient",
    "invalid": "state-invalid", "calculation_error": "state-error",
}
_DIRECTION_CLASSES = {x: f"direction-{x}" for x in ("bullish", "bearish", "neutral", "mixed", "unavailable")}
_RISK_CLASSES = {x: f"risk-{x}" for x in ("minimal", "low", "moderate", "elevated", "high", "critical", "unavailable")}
_ATTENTION_CLASSES = {x: f"attention-{x}" for x in ("none", "low", "normal", "high", "immediate", "unavailable")}
# Do not permit accidental trade instructions to pass from raw diagnostic text
# into a future HTML template.  These are display-only words; their removal has
# no effect on canonical decision data.
_FORBIDDEN = ("buy", "sell", "long", "short", "enter", "exit", "entry", "stop_loss", "take_profit", "add_position", "reduce_position", "買進", "賣出", "做多", "做空", "進場", "出場", "停損", "停利", "加碼", "減碼", "下單")


@dataclass(frozen=True, slots=True)
class DashboardPresenterConfig:
    supported_read_model_versions: frozenset[str] = frozenset({DASHBOARD_READ_MODEL_VERSION})
    supported_serialization_versions: frozenset[str] = frozenset({DASHBOARD_SERIALIZATION_VERSION})
    presenter_version: str = DASHBOARD_PRESENTER_VERSION
    section_order: tuple[DashboardSectionKey, ...] = tuple(DashboardSectionKey)
    timeframe_order: tuple[str, ...] = _TIMEFRAMES
    module_order: tuple[str, ...] = _MODULES
    warning_limit: int = 32
    secondary_reason_limit: int = 3
    supporting_factor_limit: int = 3
    blocker_limit: int = 3
    show_raw_state: bool = False
    show_source_versions: bool = True
    html_escape: bool = True
    language: str = "zh-TW"
    page_title: str = "KAM Trade V3"
    page_subtitle: str = "Trading Decision Operating System"

    def __post_init__(self) -> None:
        if (not self.supported_read_model_versions or not self.supported_serialization_versions
                or self.presenter_version != DASHBOARD_PRESENTER_VERSION
                or self.timeframe_order != _TIMEFRAMES or self.module_order != _MODULES
                or self.section_order != tuple(DashboardSectionKey)
                or min(self.warning_limit, self.secondary_reason_limit, self.supporting_factor_limit, self.blocker_limit) <= 0
                or self.language != "zh-TW"):
            raise ValueError("Invalid Dashboard presenter configuration")

    @classmethod
    def provisional(cls) -> "DashboardPresenterConfig":
        return cls()


@dataclass(frozen=True, slots=True)
class DashboardPresenterView:
    presenter_version: str
    source_version: str | None
    page_title: str
    page_subtitle: str
    display_state: str
    attention_level: str
    theme_state: DashboardThemeState
    market_overview: Mapping[str, Any]
    market_decision: Mapping[str, Any]
    timeframe_cards: tuple[Mapping[str, Any], ...]
    module_sections: tuple[Mapping[str, Any], ...]
    three_second_summary: Mapping[str, Any]
    message_banner: Mapping[str, Any]
    messages: tuple[str, ...]
    footer: Mapping[str, Any]
    accessibility: Mapping[str, Any]
    template_context: Mapping[str, Any]
    valid: bool
    warnings: tuple[str, ...]
    error_codes: tuple[str, ...]


def _text(value: Any, *, escape_html: bool = True) -> str:
    text = "—" if value is None or value == "" else str(getattr(value, "value", value))
    for forbidden in _FORBIDDEN:
        text = text.replace(forbidden, "[filtered]").replace(forbidden.title(), "[filtered]").replace(forbidden.upper(), "[filtered]")
    return escape(text, quote=True) if escape_html else text


def _score(value: Any) -> str:
    if value is None:
        return "—"
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return "—"
    return f"{numeric:.0f}" if numeric.is_integer() else f"{numeric:.1f}"


def _class(mapping: Mapping[str, str], value: Any) -> str:
    key = str(getattr(value, "value", value))
    if key not in mapping:
        raise ValueError(f"Unknown presenter state: {key}")
    return mapping[key]


def _mapping(value: Any) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return value
    raise ValueError("Expected mapping")


def _as_payload(source: DashboardReadModel | Mapping[str, Any]) -> tuple[Mapping[str, Any], str]:
    if isinstance(source, DashboardReadModel):
        if source.version != DASHBOARD_READ_MODEL_VERSION:
            raise ValueError("Unsupported Dashboard Read Model version")
        return serialize_dashboard_read_model(source, DashboardSerializationConfig.provisional()), "read_model"
    if isinstance(source, Mapping):
        return source, "serialized_payload"
    raise TypeError("Dashboard presenter accepts DashboardReadModel or serialized payload mapping")


def _theme(display_state: str, risk_level: str) -> DashboardThemeState:
    if display_state in {"invalid", "calculation_error"}:
        return DashboardThemeState.UNAVAILABLE
    if display_state in {"blocked", "stale"} or risk_level == "critical":
        return DashboardThemeState.DANGER
    if display_state in {"waiting", "market_closed"}:
        return DashboardThemeState.WAITING
    if display_state == "review_required" or risk_level in {"elevated", "high"}:
        return DashboardThemeState.CAUTION
    return DashboardThemeState.CALM if display_state == "observing" else DashboardThemeState.NORMAL


def _invalid_view(config: DashboardPresenterConfig, code: str) -> DashboardPresenterView:
    state, attention, theme = "invalid", "immediate", DashboardThemeState.UNAVAILABLE
    header = {"title": config.page_title, "subtitle": config.page_subtitle, "product_name": "KAM Trade V3", "product_type": "read-only", "evaluated_at_text": "—", "market_status_text": "invalid", "display_state": state, "attention_level": attention, "badge_text": "資料不可用", "badge_class": "state-invalid"}
    accessibility = {"page_landmark_label": "KAM Trade V3 dashboard", "summary_aria_label": "市場摘要", "decision_aria_label": "市場決策", "timeframe_group_label": "四個週期", "module_group_label": "四個分析模組", "message_region_label": "系統訊息", "status_live_mode": "assertive", "language": config.language, "heading_order_valid": True}
    context = {"section_order": tuple(x.value for x in config.section_order), "header": header, "market_overview": {}, "summary": {}, "decision": {}, "timeframe_cards": (), "module_sections": (), "message_banner": {"visible": True, "severity": "critical", "title": "資料不可用", "short_text": "展示資料無法驗證。", "source_text": "presenter", "timeframe_text": "—", "state_class": "state-invalid", "aria_live": "assertive", "dismissible": False}, "messages": ("展示資料無法驗證。",), "footer": {"presenter_version": config.presenter_version}, "accessibility": accessibility, "theme_state": theme.value}
    return DashboardPresenterView(config.presenter_version, None, config.page_title, config.page_subtitle, state, attention, theme, {}, {}, (), (), {}, context["message_banner"], context["messages"], context["footer"], accessibility, context, False, (), (code,))


def build_dashboard_presenter(source: DashboardReadModel | Mapping[str, Any], config: DashboardPresenterConfig) -> DashboardPresenterView:
    """Return a deterministic, HTML-safe, template-friendly presentation view.

    Invalid sources do not raise into a rendering route: they produce a stable,
    unavailable presentation view.  Invalid configuration remains a programmer
    error and is rejected at construction time.
    """
    if not isinstance(config, DashboardPresenterConfig):
        raise TypeError("config must be DashboardPresenterConfig")
    try:
        payload, source_kind = _as_payload(source)
        serialization_version = payload.get("serialization_version")
        read_model_version = payload.get("read_model_version")
        if serialization_version not in config.supported_serialization_versions or read_model_version not in config.supported_read_model_versions:
            raise ValueError("source_version_mismatch")
        frames = payload.get("timeframe_views")
        if not isinstance(frames, list) or [f.get("timeframe") for f in frames if isinstance(f, Mapping)] != list(config.timeframe_order) or len(frames) != 4:
            raise ValueError("invalid_timeframes")
        state = str(payload.get("display_state"))
        attention = str(payload.get("attention"))
        decision = _mapping(payload.get("market_decision"))
        overview = _mapping(payload.get("market_overview"))
        _class(_DISPLAY_CLASSES, state); _class(_ATTENTION_CLASSES, attention)
        risk_level = str(decision.get("risk_level", "unavailable"))
        direction = str(decision.get("direction", "unavailable"))
        _class(_RISK_CLASSES, risk_level); _class(_DIRECTION_CLASSES, direction)
        theme = _theme(state, risk_level)
        evaluated_at = _text(payload.get("evaluated_at"), escape_html=config.html_escape)
        header = {"title": config.page_title, "subtitle": config.page_subtitle, "product_name": "KAM Trade V3", "product_type": "read-only", "evaluated_at_text": evaluated_at, "market_status_text": _text(state), "display_state": state, "attention_level": attention, "badge_text": _text(attention), "badge_class": _class(_DISPLAY_CLASSES, state)}
        summary_source = _mapping(payload.get("summary"))
        summary = {"headline": _text(summary_source.get("market_state")), "direction_text": _text(summary_source.get("direction_text")), "confidence_text": _text(summary_source.get("confidence_text")), "risk_text": _text(summary_source.get("risk_text")), "next_step_text": _text(summary_source.get("next_step_text")), "attention_text": _text(summary_source.get("attention_text")), "state_class": _class(_DISPLAY_CLASSES, state), "aria_label": "市場三秒摘要", "valid": bool(payload.get("valid"))}
        decision_view = {"direction_text": _text(direction), "direction_class": _class(_DIRECTION_CLASSES, direction), "confidence_text": _text(decision.get("confidence_level")), "confidence_score_text": _score(decision.get("confidence_score")), "confidence_class": _class(_DISPLAY_CLASSES, str(decision.get("confidence_state", "invalid"))) if str(decision.get("confidence_state", "invalid")) in _DISPLAY_CLASSES else "state-invalid", "risk_text": _text(risk_level), "risk_score_text": _score(decision.get("risk_score")), "risk_class": _class(_RISK_CLASSES, risk_level), "next_step_text": _text(decision.get("next_step")), "next_step_class": _class(_DISPLAY_CLASSES, str(decision.get("next_step_state", "invalid"))) if str(decision.get("next_step_state", "invalid")) in _DISPLAY_CLASSES else "state-invalid", "priority_text": _text(decision.get("next_step_priority")), "primary_reason_text": _text(decision.get("primary_reason")), "secondary_reason_texts": tuple(_text(x) for x in decision.get("secondary_reasons", ())[:config.secondary_reason_limit]), "supporting_factor_texts": tuple(_text(x) for x in decision.get("supporting_factors", ())[:config.supporting_factor_limit]), "blocker_texts": tuple(_text(x) for x in decision.get("blockers", ())[:config.blocker_limit]), "display_state": state, "valid": bool(payload.get("valid"))}
        cards = []
        modules = []
        titles = {"position": ("Position", "市場位置是否可確認？"), "trend": ("Trend", "趨勢結構是否一致？"), "structure": ("Structure", "結構是否已確認？"), "timing": ("Timing", "目前資料是否可確認？")}
        for frame in frames:
            f = _mapping(frame); f_state = str(f.get("display_state")); f_direction = str(f.get("direction", "unavailable")); f_risk = str(f.get("risk_level", "unavailable"))
            card = {"timeframe": _text(f.get("timeframe")), "display_label": _text(f.get("display_label")), "state_text": _text(f_state), "state_class": _class(_DISPLAY_CLASSES, f_state), "direction_text": _text(f_direction), "direction_class": _class(_DIRECTION_CLASSES, f_direction), "confidence_text": _text(f.get("confidence_level")), "confidence_score_text": _score(f.get("confidence_score")), "risk_text": _text(f_risk), "risk_score_text": _score(f.get("risk_score")), "next_step_text": _text(f.get("next_step")), "next_step_class": _class(_DISPLAY_CLASSES, state), "position_text": _text(_mapping(f.get("position")).get("headline")), "trend_text": _text(_mapping(f.get("trend")).get("headline")), "structure_text": _text(_mapping(f.get("structure")).get("headline")), "timing_text": _text(_mapping(f.get("timing")).get("headline")), "primary_reason_text": _text(f.get("primary_reason")), "warning_texts": tuple(_text(x) for x in f.get("warnings", ())[:config.warning_limit]), "aria_label": f"{_text(f.get('display_label'))} 週期狀態", "valid": bool(f.get("valid"))}
            cards.append(card)
            for name in config.module_order:
                item = _mapping(f.get(name)); title, question = titles[name]
                modules.append({"module": name, "timeframe": card["display_label"], "title": title, "question": question, "headline": _text(item.get("headline")), "state_text": _text(item.get("state")), "status_text": _text(item.get("status")), "confirmation_text": _text(item.get("confirmation_state")), "quality_text": _text(item.get("quality_state")), "short_reason": _text(item.get("short_reason")), "raw_state_text": _text(item.get("raw_state")) if config.show_raw_state else "—", "warning_texts": tuple(_text(x) for x in item.get("warnings", ())[:config.warning_limit]), "state_class": _class(_DISPLAY_CLASSES, f_state), "aria_label": f"{card['display_label']} {title}", "valid": bool(item.get("valid"))})
        warnings = tuple(_text(x) for x in payload.get("warnings", ())[:config.warning_limit])
        errors = tuple(_text(x) for x in payload.get("error_codes", ()))
        severity = "critical" if state in {"invalid", "calculation_error", "stale", "blocked"} or risk_level == "critical" else "warning" if warnings else "info"
        banner = {"visible": bool(warnings or errors or severity == "critical"), "severity": severity, "title": "系統訊息", "short_text": (errors + warnings + ("—",))[0], "source_text": source_kind, "timeframe_text": "—", "state_class": _class(_DISPLAY_CLASSES, state), "aria_live": "assertive" if severity == "critical" else "polite" if severity == "warning" else "off", "dismissible": False}
        accessibility = {"page_landmark_label": "KAM Trade V3 dashboard", "summary_aria_label": "市場三秒摘要", "decision_aria_label": "市場決策", "timeframe_group_label": "四個週期", "module_group_label": "四個分析模組", "message_region_label": "系統訊息", "status_live_mode": banner["aria_live"], "language": config.language, "heading_order_valid": True}
        footer = {"presenter_version": config.presenter_version, "source_version": read_model_version if config.show_source_versions else "—", "serialization_version": serialization_version if config.show_source_versions else "—"}
        safe_overview = {k: _text(v) for k, v in overview.items() if not isinstance(v, (dict, list, tuple))}
        context = {"section_order": tuple(x.value for x in config.section_order), "header": header, "market_overview": safe_overview, "summary": summary, "decision": decision_view, "timeframe_cards": tuple(cards), "module_sections": tuple(modules), "message_banner": banner, "messages": warnings + errors, "footer": footer, "accessibility": accessibility, "theme_state": theme.value}
        return DashboardPresenterView(config.presenter_version, read_model_version, config.page_title, config.page_subtitle, state, attention, theme, safe_overview, decision_view, tuple(cards), tuple(modules), summary, banner, warnings + errors, footer, accessibility, context, bool(payload.get("valid")), warnings, errors)
    except (KeyError, TypeError, ValueError, AttributeError) as exc:
        return _invalid_view(config, f"presenter_{type(exc).__name__.lower()}")
