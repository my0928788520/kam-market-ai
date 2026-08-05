# Paper Trading v0.1 Phase 2 Release Note

Added an offline, deterministic in-memory matching engine and immutable cash /
position ledger for Paper Trading simulation.

The release supports MARKET and LIMIT BUY/SELL simulation, full and partial
fills, local cancellation, idempotency protection, fee calculation, atomic
ledger application, and matching audit records. It deliberately adds no
networking, broker SDK, credentials, real account access, or live execution.
