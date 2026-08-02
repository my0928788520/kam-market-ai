# Replay WSGI Adapter

Version 1.0 accepts only `ReplayPresenterView` 1.0 and produces an immutable template context. All market and data display states remain HTTP 200; only route, method, and internal rendering failures use HTTP errors. Responses are UTF-8 `text/html` with `Cache-Control: no-store`. No Engine, Decision, data source, controls, or fixture loader is used.
