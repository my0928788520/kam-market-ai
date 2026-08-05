# KAM Live Read-Only v0.1 — Market Snapshot Contract

## Purpose

This Sprint defines immutable, deterministic futures market snapshots for local read-only use.
It has no network, broker, account, order, or execution capability.

## Product identity

Supported products are `TX` (臺股期貨), `MTX` (小型臺指期貨), and `TMF` (微型臺指期貨).
The default product is `TMF`.  Product identity is separate from a supplied contract identity:
TX contracts begin with `TXF`, MTX with `MXF`, and TMF with `TMF`; contract month is `YYYYMM`.
Missing or invalid contract identity produces `INVALID_CONTRACT` and is not eligible for later proposal work.

## Session, freshness, and fail-closed behavior

`TradingSession` is explicitly supplied as DAY, NIGHT, CLOSED, or UNKNOWN; local clock inference is forbidden.
Snapshots retain observed time, source time, age seconds, and freshness.  Missing timestamps, naive timestamps,
time reversal, or invalid age are `INVALID_TIMESTAMP` with UNKNOWN freshness.  STALE and EXPIRED retain their
own fail-closed statuses.

## Read-only source and safety

`MarketDataReadOnlySource` exposes only `read_snapshot(product_code)` and `list_available_products()`.
`OfflineDemoMarketDataSource` has independent fixed TX, MTX, and TMF values and exists only for local testing.
All snapshot security flags are fixed false: account connection, broker connection, live orders, and trading.

## Later integration

Later read-only Sprints may consume a valid snapshot through an explicit adapter.  This Sprint does not connect
Rule Adapter, Proposal, Matching, Ledger, Account Center, WebSocket, broker SDK, or real market data.
