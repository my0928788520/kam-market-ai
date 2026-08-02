# Market Data Provider Adapter — Sprint 5 Phase 2

## Scope

The adapter accepts only in-memory offline content. Supported source encodings are `replay`, `fixture`, `json`, and `csv`. It produces the Phase 1 `MarketDataProviderResponse` contract and has no provider client or external side effect.

## Input schema

Each row must include `instrument`, `timeframe`, `opened_at`, `closed_at`, `open`, `high`, `low`, `close`, `volume`, and `source_record_id`. `closed` is optional and defaults to `true`. Timestamps are ISO-8601; numeric values are converted to `Decimal` before the contract validates them.

Replay and fixture content is a sequence of mappings. JSON content is an array of the same mappings. CSV content has the same field names as headers.

## Policy

The adapter selects only matching instrument/timeframe/range records and canonicalizes them by `(opened_at, source_record_id)`. No matching record returns `insufficient_data` with `NO_MATCHING_OFFLINE_BARS`. Invalid JSON, wrong row shape, invalid values, duplicate canonical keys, or incomplete bars return a deterministic `blocked` response. It never repairs or silently discards malformed rows.

## Non-goals

No filesystem access, HTTP, WebSocket, SDK, credentials, live provider, broker, account, order, execution, persistence, or trading behavior is included.
