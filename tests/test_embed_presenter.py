from kam_market_ai.live_read_only.decision_presentation import SelectedSnapshotDecisionPresenter
from kam_market_ai.live_read_only.market_snapshot import OFFLINE_DEMO_MARKET_DATA_SOURCE, MarketSnapshotStatus
from kam_market_ai.live_read_only.runtime_market_source import RuntimeMarketSourceStatus
from kam_market_ai.paper_trading.embed_presenter import EmbedPagePresenter
from kam_market_ai.public_deployment import PublicEmbedConfig

def page(code="TMF", status=RuntimeMarketSourceStatus.READY, drawer=True):
    snapshot=OFFLINE_DEMO_MARKET_DATA_SOURCE.read_snapshot(code); decision=SelectedSnapshotDecisionPresenter().present(snapshot)
    return EmbedPagePresenter().render(EmbedPagePresenter().build_model(snapshot, decision, status, PublicEmbedConfig(enable_account_drawer=drawer), code))

def test_embed_selector_responsive_safety_and_drawer_switch():
    html=page()
    for link in ("/embed?instrument=TX","/embed?instrument=MTX","/embed?instrument=TMF","overflow-x:hidden","@media(max-width:700px)","期貨帳戶｜資金安全","唯讀模式","禁止真實下單"): assert link in html
    assert "class='account-trigger'" not in page(drawer=False)

def test_embed_fail_closed_escapes_dynamic_data_and_has_no_sensitive_or_trade_text():
    snapshot=OFFLINE_DEMO_MARKET_DATA_SOURCE.read_snapshot("TMF"); decision=SelectedSnapshotDecisionPresenter().present(snapshot)
    html=EmbedPagePresenter().render(EmbedPagePresenter().build_model(snapshot,decision,RuntimeMarketSourceStatus.RESERVED,PublicEmbedConfig(),"TMF",runtime_label="<script>bad</script>"))
    for text in ("資料不足／無法判讀","不可判讀","等待資料","資料不足","等待資料恢復","&lt;script&gt;bad&lt;/script&gt;"): assert text in html
    for forbidden in ("TEST_ONLY_TOKEN","api_key","Authorization","C:\\Users\\","traceback","git commit","account_connected=false","trading_enabled=false","買進","賣出","開倉","加碼","平倉","可執行"): assert forbidden not in html
