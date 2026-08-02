# Market Data Scan Engine — Sprint 5 Phase 4

## Scope

The Scan Engine plans and executes deterministic reads over the existing Historical Feed and explicitly supplied offline dataset. It does not access a filesystem, network, SDK, or any live source.

## Plan

`MarketDataScanRequest` declares the provider contract, offline dataset, instruments, timeframe, time range, `as_of`, and fixed batch size. `build_market_data_scan_plan` canonicalizes instruments (trimmed, upper-case, sorted, unique) and creates sequential batches. The plan verifies non-empty instruments, valid time range, `as_of` boundary, and provider timeframe capability. Invalid input yields a `blocked` plan with deterministic issue codes.

`plan_hash` includes provider/dataset lineage, canonical instruments and batches, range, timeframe, version, and issue codes. It does not use runtime time or random IDs.

## Execution

`execute_market_data_scan` creates only provider requests and invokes `read_historical_feed`. A feed `blocked` result blocks its batch, stops later batches, and labels them `skipped`. Missing offline data is a completed-with-issues result; it does not become a successful scan. `scan_hash` includes plan hash, batch outcomes, feed hashes, and issue codes.

## Non-goals

No HTTP, WebSocket, filesystem discovery, SDK, live data provider, broker, account, order, execution, persistence, or trading behavior.
