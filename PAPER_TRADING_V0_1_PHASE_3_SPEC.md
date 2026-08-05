# Paper Trading v0.1 Phase 3 — Strategy-to-Paper Order Proposal

Phase 3 converts an explicit offline strategy input into an immutable,
SHA-256-hashed proposal. It is not an order. `HOLD` cannot convert, all other
proposals require explicit manual confirmation, are expiry-checked, and stop
when emergency stop is active. Only a confirmed proposal produces the existing
Phase 1 paper request for the Phase 2 in-memory matcher.

All timestamps are UTC and all financial values are Decimal. The contract fixes
dry-run and disables live order, broker connection, and trading enablement.
