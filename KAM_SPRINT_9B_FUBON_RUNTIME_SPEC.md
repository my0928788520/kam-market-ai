# KAM Sprint 9B — Fubon Live Runtime and Dashboard

## Purpose

Sprint 9B carries the Sprint 9A-verified TX, MTX, and TMF trade stream into the
existing provider-neutral `LiveMarketDataRecord` and immutable `MarketSnapshot`
contracts. It is a Windows-local, read-only runtime source for the KAM dashboard.

## Explicit activation

The default remains `offline-demo`. Live startup requires both
`--market-source fubon-live` and `--live`. Authorization remains in the existing
bootstrap boundary, and only `AuthorizedMarketDataClients` crosses into the
runtime. Contract discovery is repeated before every startup; no contract month
is guessed or persisted.

## Runtime lifecycle

The runtime attaches listeners, connects, authenticates, subscribes by verified
symbol, waits for subscription acknowledgements, and requires at least one fresh
trade event for each of TX, MTX, and TMF before it reports `READY`. It caches only
normalized product identity, contract identity, provider time, last price, and
volume. Raw provider payloads and credentials are never stored.

On provider error or unexpected disconnect, the runtime becomes `DEGRADED` and
`MarketSnapshot` fails closed as `CLIENT_UNAVAILABLE`. Stale data becomes `STALE`
after 60 seconds and `EXPIRED` after 300 seconds. Shutdown unsubscribes by channel
ID, disconnects, and removes listeners.

## Dashboard boundary

The dashboard shows the live source, verified contract, last price, volume,
provider time, session, and the four fixed non-trading safety states. The page
refreshes every three seconds while `fubon-live` is selected.

A trade tick is not enough to derive KAM direction. Until historical candles and
the five-timeframe Rule Engine are connected, direction, control, cycle, trend
health, proposal, matching, position, and P/L remain explicitly unavailable. No
offline decision or proposal may be displayed as if it were derived from live
market data.

## Non-trading boundary

`account_connected`, `broker_connected`, `trading_enabled`, and
`live_order_allowed` remain false. The runtime contains no account, balance,
position, order, cancel, modify, or execution method.
