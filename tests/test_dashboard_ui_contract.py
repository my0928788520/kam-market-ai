from kam_market_ai.dashboard.ui_contract import CSS_TOKENS, DASHBOARD_UI_VERSION, DECISION_IDS, MODULE_IDS, SECTION_IDS, TIMEFRAME_IDS, DashboardUIConfig


def test_ui_contract_has_fixed_versions_ids_and_tokens():
    assert DASHBOARD_UI_VERSION == "1.0"
    assert SECTION_IDS == ("dashboard-status-banner", "dashboard-header", "dashboard-three-second-summary", "dashboard-market-decision", "dashboard-timeframes", "dashboard-modules", "dashboard-messages", "dashboard-footer")
    assert len(DECISION_IDS) == len(TIMEFRAME_IDS) == len(MODULE_IDS) == 4
    assert "--page-bg" in CSS_TOKENS and DashboardUIConfig.provisional().language == "zh-TW"
