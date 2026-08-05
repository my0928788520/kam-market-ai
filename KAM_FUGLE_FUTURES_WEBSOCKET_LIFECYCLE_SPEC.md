# KAM Live Read-Only v0.1 — Sprint 6: Fugle Futures WebSocket Lifecycle

## Scope

Sprint 6 defines a transport-injected, read-only lifecycle for futures market data. Runtime stays offline-demo by default; this Sprint does not connect a real WebSocket or integrate the Trading Terminal.

## State machine

The lifecycle begins `DISABLED` unless explicitly enabled, otherwise `IDLE`. Legal transitions are audited: `CONNECTING → AUTHENTICATING → CONNECTED → SUBSCRIBING → READY`. Transport, authentication, subscription, receive, and close failures move to `DEGRADED` or `FAILED`. Partial required subscriptions are never `READY`. Illegal transitions raise a stable lifecycle error.

## Transport and authentication boundary

The provider-neutral transport permits only `connect`, `authenticate`, `subscribe`, `receive`, and `close`. It has no order, account, position, balance, or trade method. API-key configuration is explicitly injected, redacted from repr, omitted from events/errors, and never read from environment variables.

## Subscription registry

TX, MTX, and TMF symbols are resolved exclusively through the Sprint 5 `FugleFuturesSymbolRegistry`. Subscription snapshots retain requested, subscribed, rejected symbols, timestamp, and registry version.

## Cache and records

Received payloads are mapped through Sprint 5's payload mapper into `LiveMarketDataRecord`, then placed in a thread-safe cache. Newer per-product timestamps replace prior data; duplicates and out-of-order values cannot overwrite it. Reads return nothing unless lifecycle is `READY` and cached data is fresh.

## Reconnect policy

The injected policy defines bounded deterministic backoff (`max_attempts`, initial/max delay, multiplier, disabled jitter, reset threshold). The sleeper is injected; tests do not sleep. Exhaustion ends at `FAILED`, never an infinite reconnect loop.

## Fail-closed and safety

Malformed/unsupported messages, timeouts, stale cache data, cache misses, partial subscriptions, disconnects, and lifecycle errors cannot produce usable data. All snapshots/events retain no account or trade capability; market-data authentication never indicates broker/account connectivity.

## Sprint 7 handoff

Sprint 7 may explicitly opt into a runtime transport and convert fresh cached records through the Sprint 4 adapter. It must preserve the lifecycle state gate, credential redaction, and no-trading boundary.
