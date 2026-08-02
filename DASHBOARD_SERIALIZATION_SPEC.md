# Dashboard Serialization Contract

Dashboard Serialization 1.0 converts only `DashboardReadModel 1.0` into deterministic JSON-safe data. Decimal defaults to stable string form, aware datetimes use ISO 8601, enums use `.value`, tuples become arrays, and non-finite Decimal or naive datetimes fail closed. `timeframe_views` is an ordered array: 15m, 60m, 1d, 1w. This layer creates no UI, route, API, websocket, market-data call, account action, or order.
