# Historical Feed / Offline Dataset Layer — Sprint 5 Phase 3

## Scope

`historical_feed.py` is a pure in-memory layer over the Sprint 5 offline provider adapter. It accepts explicit Replay, Fixture, JSON, or CSV dataset content. It does not discover files, open paths, call an SDK, or make any network request.

## Dataset and feed lineage

`OfflineHistoricalDataset` has a dataset ID, version, timezone-aware capture time, and an `OfflineMarketDataSource`. Its canonical payload and SHA-256 `dataset_hash` identify the exact supplied dataset content. Mapping key order does not affect the hash.

`read_historical_feed` checks that the provider's research source kind agrees with the dataset encoding policy, then delegates to `adapt_offline_market_data`. `HistoricalFeedResult` carries the dataset identity, dataset hash, provider response, response hash, and deterministic feed hash.

## Fail-closed policy

Replay data requires a replay provider contract. Fixture, JSON, and CSV data require a fixture provider contract. A mismatch returns `blocked` with `DATASET_SOURCE_KIND_MISMATCH`. Adapter parsing/validation failures remain blocked; no content is repaired or fetched from another source.

## Non-goals

No filesystem scanning, HTTP, WebSocket, live data provider, credentials, broker, account, order, execution, persistence, or trading behavior.
