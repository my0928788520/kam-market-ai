# Paper Trading v0.1 Phase 2 — In-Memory Matching Engine

## Scope

Phase 2 is a deterministic, offline-only simulation layer. It accepts only the
Phase 1 `PaperTradingOrderRequest`, supplied `OfflineMarketSnapshot` values,
and in-memory ledger state. It has no network, broker, credential, account, or
production-trading integration.

## Matching policy

- MARKET orders use the supplied ask for BUY and bid for SELL.
- LIMIT BUY fills only at or below the request limit; LIMIT SELL fills only at
  or above the request limit.
- Available snapshot quantity bounds a fill, producing `FILLED` or
  `PARTIALLY_FILLED`; a non-crossing LIMIT order is `OPEN`.
- Cancellation is a local immutable `CANCELLED` result, never an external API.
- Fill identity, ordering, serialization, and hashes are SHA-256 based and
  deterministic for equal input.

## Safety boundary

Every request first passes Phase 1 safety evaluation. Emergency stop,
idempotency reuse, missing snapshot, insufficient cash, insufficient position,
or invalid fee input returns a fail-closed `REJECTED` result. Failed matching
leaves the source ledger unchanged. The model fixes `dry_run=true`,
`live_order_allowed=false`, `broker_connected=false`, and
`account_credentials_allowed=false`.

## Ledger policy

Cash and position updates are a single immutable transaction. BUY decreases
cash by notional plus fees; SELL increases cash by notional less fees. Negative
cash and short positions are rejected unless the explicitly represented ledger
flags permit them. Cash entries and positions are canonicalized and auditable.
