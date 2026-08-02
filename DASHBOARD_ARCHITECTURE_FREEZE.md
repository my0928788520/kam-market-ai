# Sprint 3 Architecture Freeze

The frozen V1 matrix is: Read Model 1.0, Serialization 1.0, Fixture 1.0,
Presenter 1.0, WSGI Adapter 1.0 and UI 1.0.

Canonical flow: Decision outputs → Read Model → Serialization → Presenter →
WSGI context → static HTML/CSS. The presentation modules do not import decision
engines or brokerage dependencies. Fixed timeframes are 15m, 60m, 1d and 1w;
fixed module families are Position, Trend, Structure and Timing.

Unsupported or incomplete presentation input fails closed. Market invalidity is
HTTP 200 with an unavailable display; route/method/server faults remain 404/405/
500. No account, order, transaction control, polling, API addition, WebSocket or
client-side market calculation belongs to this freeze.
