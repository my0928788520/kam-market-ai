# Sprint 4 Replay Architecture Freeze

## Status

Frozen after Phase 5C acceptance. Replay is an offline, deterministic, read-only research system, not a production trading system.

## Dependency flow

`Scenario → Timeline → Runner → Frame → Evaluator → Decision evaluation → Read Model → Comparison → Presenter → WSGI Context → HTML`.

Each layer has one direction of dependency. UI consumes Presenter only; it does not call Runner, Evaluator, Engine, Decision, network, brokerage, account, database, or scheduler code. IDs and hashes are deterministic; data gaps block rather than auto-fill; source corrections are markers and do not rewrite earlier frames. WSGI responses use HTTP 200 for data states and `Cache-Control: no-store`.

## Freeze conditions and limitations

All tests passed twice in Phase 5C. Any breaking contract change requires a major version and a new acceptance run. Replay has no historical/live market provider, calendar, controls, navigation, charts, API, WebSocket, account simulation, PnL, order capability, or transaction advice.
