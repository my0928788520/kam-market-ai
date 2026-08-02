# Market Data Provider Contract — Sprint 5 Phase 1

## Scope

This contract is a pure, offline research boundary for deterministic historical fixture and replay data. It does not implement a provider and does not perform file, network, SDK, broker, account, order, or execution work.

## Contract

`MarketDataProviderContract` accepts only `fixture` and `replay` sources. `research_only` is fixed to `true`; `network_enabled` and `live_provider_enabled` are fixed to `false`.

`MarketDataRequest` requires an explicit provider ID, instrument, supported timeframe, timezone-aware `[start_at, end_at)` range, and timezone-aware `as_of` boundary.

`MarketDataBar` uses `Decimal` for OHLCV values and requires closed, timezone-aware bars with internally valid OHLC data. Floats are not accepted as prices.

`MarketDataProviderResponse` verifies provider/request identity, supported timeframe, canonical bar ordering, no duplicate bar key, requested-range membership, and `as_of` membership. Non-ready responses require canonical issue codes; ready responses require at least one bar and no issues.

## Determinism and fail-closed behavior

The response canonical payload serializes timestamps in UTC, uses decimal strings, preserves declared bar order only after validation, and hashes compact sorted JSON with SHA-256. Invalid versions, unsafe capabilities, incomplete bars, bad ranges, unsupported timeframe, mismatched providers, duplicate/noncanonical bars, and missing non-ready evidence raise `ValueError`.

## Explicit non-goals

- No network or live provider implementation.
- No credentials, SDK imports, polling, or file reads.
- No broker, account, order, portfolio, or trading behavior.
- No persistence, normalization adapter, or dashboard integration.
