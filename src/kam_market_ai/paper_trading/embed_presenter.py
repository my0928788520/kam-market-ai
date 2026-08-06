"""Self-contained, read-only blog embed presenter."""
from __future__ import annotations
from dataclasses import dataclass
from html import escape
from typing import Iterable

from kam_market_ai.live_read_only.decision_presentation import DecisionPresentation
from kam_market_ai.live_read_only.market_snapshot import MarketSnapshot, MarketSnapshotStatus
from kam_market_ai.live_read_only.runtime_market_source import RuntimeMarketSourceStatus
from kam_market_ai.public_deployment import PublicEmbedConfig

_PRODUCTS = (("TX", "大台 TX"), ("MTX", "小台 MTX"), ("TMF", "微台 TMF"))
_FORBIDDEN_ACTIONS = ("買進", "賣出", "開倉", "加碼", "平倉", "可執行")

@dataclass(frozen=True, slots=True)
class EmbedSecurityModel:
    read_only: bool = True
    live_order_allowed: bool = False

@dataclass(frozen=True, slots=True)
class EmbedRuntimeStatusModel:
    label: str
    status: RuntimeMarketSourceStatus

@dataclass(frozen=True, slots=True)
class EmbedProductSelectorModel:
    selected_product_code: str
    links: tuple[tuple[str, str], ...]

@dataclass(frozen=True, slots=True)
class EmbedDecisionModel:
    direction: str
    control: str
    cycle: str
    timeframes: tuple[str, ...]
    trend_health: str
    next_step: str

@dataclass(frozen=True, slots=True)
class EmbedPageModel:
    snapshot: MarketSnapshot
    decision: EmbedDecisionModel
    runtime: EmbedRuntimeStatusModel
    selector: EmbedProductSelectorModel
    security: EmbedSecurityModel
    account_drawer_enabled: bool

class EmbedPagePresenter:
    def build_model(self, snapshot: MarketSnapshot, decision: DecisionPresentation, runtime_status: RuntimeMarketSourceStatus, config: PublicEmbedConfig, selected_product_code: str = "TMF", allow_account_drawer: bool = True, runtime_label: str = "離線示範行情") -> EmbedPageModel:
        unavailable = snapshot.status is not MarketSnapshotStatus.READY or runtime_status is not RuntimeMarketSourceStatus.READY
        fallback = EmbedDecisionModel("資料不足／無法判讀", "不可判讀", "不可判讀", ("等待資料",) * 5, "資料不足", "等待資料恢復")
        rendered = fallback if unavailable else EmbedDecisionModel(decision.direction.label, decision.control.label, decision.cycle.label, tuple(item.label for item in decision.timeframes), decision.trend_health.label, decision.next_step.label)
        links = tuple((code, f"/embed?instrument={code}") for code, _ in _PRODUCTS)
        return EmbedPageModel(snapshot, rendered, EmbedRuntimeStatusModel(runtime_label, runtime_status), EmbedProductSelectorModel(selected_product_code, links), EmbedSecurityModel(), allow_account_drawer and config.enable_account_drawer)

    def render(self, model: EmbedPageModel) -> str:
        s, d = model.snapshot, model.decision
        selector = "".join(f"<a class='selector {'active' if code == model.selector.selected_product_code else ''}' href='{escape(url, quote=True)}'>{escape(code)}</a>" for code, url in model.selector.links)
        frames = "".join(f"<li>{escape(value)}</li>" for value in d.timeframes)
        drawer = "<button class='account-trigger' type='button'>期貨帳戶｜資金安全</button><aside hidden></aside>" if model.account_drawer_enabled else ""
        return f"""<!doctype html><html lang='zh-Hant-TW'><head><meta charset='utf-8'><title>KAM Trading Terminal Embed</title><style>
*{{box-sizing:border-box}}body{{margin:0;overflow-x:hidden;background:#07101d;color:#eaf2ff;font:14px system-ui}}main{{max-width:1440px;margin:auto;padding:16px}}.selector{{display:flex;flex-wrap:wrap;gap:8px}}.selector a,.account-trigger{{padding:7px 11px;border:1px solid #345;border-radius:8px;color:inherit;text-decoration:none;background:#101d2e}}.active{{border-color:#ee526f}}.grid{{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px}}section{{min-width:0;border:1px solid #1f3854;border-radius:12px;padding:12px;background:#0c1727}}strong{{font-size:20px}}@media(max-width:700px){{main{{padding:10px}}.grid{{grid-template-columns:1fr}}.account-trigger{{width:calc(100vw - 20px)}}}}</style></head><body><main>
<header><h1>KAM Trading Terminal</h1><div>{selector}</div><p>{escape(model.runtime.label)}｜唯讀模式｜禁止真實下單</p>{drawer}</header>
<section><b>{escape(s.instrument_name)}</b>｜{escape(str(s.contract_code or '—'))}｜價格 {escape(str(s.last_price or '—'))}｜量 {escape(str(s.volume or '—'))}</section>
<div class='grid'><section><h2>市場方向</h2><strong>{escape(d.direction)}</strong></section><section><h2>多空控制權</h2><strong>{escape(d.control)}</strong></section><section><h2>市場循環位置</h2><strong>{escape(d.cycle)}</strong></section><section><h2>五週期</h2><ul>{frames}</ul></section><section><h2>趨勢健康度</h2><strong>{escape(d.trend_health)}</strong></section><section><h2>唯一下一步</h2><strong>{escape(d.next_step)}</strong></section></div></main></body></html>"""
