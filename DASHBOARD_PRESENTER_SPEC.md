# Dashboard Presenter Contract

Version: `1.0`.

`build_dashboard_presenter` accepts exactly one canonical source: a
`DashboardReadModel 1.0` or a `DashboardSerializedPayload 1.0` mapping. It is
read-only and has no engine, account, quote, order, API, or WSGI-route work.

The result is a typed `DashboardPresenterView` with a template context in this
fixed order: header, market overview, three-second summary, market decision,
15m/60m/1d/1w cards, Position/Trend/Structure/Timing detail sections, messages,
and footer. All rendered values are strings, tuples, or mappings; no Decimal or
datetime object is exposed to a template.

Display, direction, risk, and attention values use closed semantic CSS mappings.
Themes express operational availability only: normal/calm, waiting, caution,
danger, or unavailable. Direction is never a safety or colour guarantee.

The page header is `KAM Trade V3` / `Trading Decision Operating System`. The
accessibility contract sets `zh-TW`, stable labels for summary, decision,
timeframes, modules and messages, plus an appropriate live-region mode. Raw
state, warnings, and reason text are HTML escaped and transaction-like display
terms are filtered. Unsupported versions, missing/duplicate timeframes, unknown
states, malformed data, or unsafe input produce an unavailable, fail-closed view.
