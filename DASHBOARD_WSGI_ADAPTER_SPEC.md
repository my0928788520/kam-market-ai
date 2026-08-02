# Dashboard WSGI Adapter Contract

Version: `1.0`.

`build_dashboard_wsgi_context` only turns an injected `DashboardPresenterView`
into an existing WSGI template context. It does not select routes, import a
decision engine, query a position, or render HTML.

Its successful dashboard response is `200` with `Content-Type: text/html;
charset=utf-8` and `Cache-Control: no-store`. Stale, blocked, critical-risk and
invalid-source dashboard views are still `200`, so a user receives an explicit
unavailable page. Existing route-not-found and method-not-allowed handling remain
the owner of `404` and `405`; only a broken adapter input returns its `500`
context.

Fixture previews are development-only, opt-in, and limited to a fixed whitelist.
Names containing paths or traversal are rejected; only a named JSON file inside
the supplied fixture directory may be read. Production configuration blocks all
fixture previews.
