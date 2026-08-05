# KAM Live Read-Only v0.1 — Sprint 5: Fugle Futures Read-Only Client

## Scope

This Sprint adds provider infrastructure only. `FugleFuturesReadOnlyClient` maps injected, read-only raw payloads to provider-neutral `LiveMarketDataRecord`, which Sprint 4 then maps to `MarketSnapshot`. It does not start a WebSocket lifecycle, connect, authenticate, subscribe, run a thread/event loop, read an account, or create trading capability.

## Provider boundary

The client implements `LiveMarketDataClientProtocol` with only `fetch_latest(product_code)` and `list_products()`. Provider SDK imports are isolated to the delayed `FugleFuturesSdkFactory`; SDK types never enter `MarketSnapshot`, `LiveMarketDataRecord`, Decision Presentation, Operator UI, Rule Adapter, or Account Center.

## Transport injection

`FugleFuturesTransportProtocol` has only `fetch_latest_raw(symbol)`. Unit tests use `FakeFugleFuturesTransport`; it is deterministic and performs no I/O. Sprint 6 owns any WebSocket lifecycle and must not be introduced here.

## Symbol registry

`FugleFuturesSymbolRegistry` resolves TX, MTX, and TMF to versioned fixture identities containing provider symbol, contract code/month, effective time, source, and registry version. Unknown product or symbol mismatches fail closed. These are fixtures, not a claim about a current production contract.

## Payload mapping

`FugleFuturesPayloadMapper` requires a matching symbol, last price, source timestamp, observed timestamp, valid session, and valid market status. It maps provider fields into decimals and timezone-aware `LiveMarketDataRecord` values. Unknown/missing/malformed fields, future timestamps, invalid timestamp units, or unsupported values raise a stable provider-neutral error.

## Credential handling

`api_key` is config-only, has `repr=False`, is never serialized or logged, and is not placed in HTML, exceptions, or domain records. Tests use only `TEST_ONLY_TOKEN`. A disabled config is the default and fails closed; missing key also fails closed.

## Safety

The provider has no order, cancellation, amendment, close-position, account, balance, position, or broker trading methods. Mapping through Sprint 4 keeps all account/broker/trading flags false. A market-data authentication key never means a broker connection.

## Future work

Sprint 6 may supply a lifecycle-managed transport to this protocol. It must retain the same injected transport boundary, registry validation, credential redaction, and fail-closed conversion to Sprint 4 snapshot statuses.
