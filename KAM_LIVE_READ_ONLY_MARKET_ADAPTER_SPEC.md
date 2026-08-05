# KAM Live Read-Only v0.1 — Sprint 4: Live Market Adapter Contract

## Purpose

Sprint 4 defines a replaceable, read-only boundary from a future market-data provider to the existing immutable `MarketSnapshot` contract. It ships no provider SDK integration, WebSocket, network request, credential handling, broker account access, or trading operation.

## Boundary

`LiveMarketDataClientProtocol` exposes only `fetch_latest(product_code)` and `list_products()`. `LiveMarketDataAdapter` implements the existing `MarketDataReadOnlySource` protocol and maps provider-neutral `LiveMarketDataRecord` values into `MarketSnapshot`.

No third-party SDK class enters the domain model. A later Fugle integration must be an infrastructure client implementing this protocol, outside this Sprint's adapter/domain types.

## Mapping and freshness

Records contain product identity, contract identity, UTC-aware provider/observed timestamps, session/status, OHLC, last price, volume, and source name. The adapter derives age solely from supplied timestamps: fresh through `stale_after_seconds`, stale through `expire_after_seconds`, and expired afterwards. It never calls a clock or network API.

## Fail-closed behavior

Client unavailable, timeout, malformed payload, unknown session/status, missing identity/timestamp, timestamp reversal, stale, expired, and unsupported product always produce a deterministic non-`READY` `MarketSnapshot`. UI callers never receive an uncaught provider exception. A non-ready snapshot cannot be considered actionable by the presentation layer.

## Source selection

`MarketSourceSelection` names `offline-demo`, `fake-live`, and `future-live`. Default selection is `offline-demo`. Selecting either live mode requires an explicit adapter configured for exactly that mode; environment variables cannot activate it implicitly.

## Safety boundary

The adapter has no order, cancellation, modification, close-position, account, credential, broker client, or network implementation. Every mapped snapshot keeps `account_connected`, `broker_connected`, `live_order_allowed`, and `trading_enabled` false.

## Future Fugle integration

A future Fugle client may implement `LiveMarketDataClientProtocol` and be explicitly passed to `LiveMarketDataAdapter`. It must remain read-only, translate SDK payloads before crossing the protocol boundary, and preserve all fail-closed behavior.
