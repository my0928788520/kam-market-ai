# Dashboard Read Model Contract

The V3 Dashboard Read Model is a typed, deterministic, read-only projection of Contract 1.0, Confidence 1.0, Risk 1.0, and Next Step 1.0. It does not add a UI, server, API, market-data call, account action, or order capability.

`build_dashboard_read_model` validates source types, versions and one timezone-aware evaluation timestamp. Any mismatch yields an invalid/unavailable display model. The model provides Market Overview, Market Decision, four fixed timeframe views, module cards, three-second summary, display state, attention and source lineage. Risk and confidence remain independently displayed; risk is never computed as `100 - confidence`.

Display state is fail-closed and prioritizes invalid, stale, blocked, waiting and observing. Text mappings and labels are typed provisional configuration. No model field represents a buy/sell, long/short, entry/exit, stop, target, or position-size recommendation.
