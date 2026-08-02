# Dashboard UI Contract

UI version: `1.0`. The V3 UI is static HTML/CSS rendered only from an injected
Dashboard Presenter template context through the existing WSGI application.
It has no browser calculation, polling, WebSocket, REST endpoint, account
control, market query, or transaction control.

The fixed DOM sequence is: global status banner, header, three-second summary,
market decision, four timeframe cards, four module cards, messages, and footer.
The stable section and card identifiers are declared in `ui_contract.py`.
The screen uses state and availability classes, not direction-based safety
claims. It includes `zh-TW`, one h1, main landmark, labels, skip link, focus
styling, progress-bar ARIA, live status banner and reduced-motion CSS.

Responsive CSS supports mobile single-column layout, tablet two-column layout,
and 1024+ four-column cards. Renderer failures are HTTP 500; unavailable market
states remain a normal HTTP 200 fail-closed dashboard page with `no-store`.
