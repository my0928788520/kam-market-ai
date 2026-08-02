# Market Data Scan Result / Read Model — Sprint 5 Phase 5

## Scope

The Scan Result Read Model is an immutable projection of an already-produced `MarketDataScanResult`. It does not execute a scan, re-read a dataset, persist data, or access any external system.

## Deterministic serialization

`build_market_data_scan_result_read_model` canonicalizes batch order by index, feed order by instrument/hash, issue codes, and requested instruments. The model's `serialize()` method emits compact sorted JSON. `result_hash` is SHA-256 of the canonical payload, which contains scan plan/result hashes plus provider and dataset lineage.

## Compatibility and fail-closed behavior

Both Scan Engine and Read Model versions must exactly match their supported versions. Unsupported result type/version, duplicate/noncanonical batch indexes, inconsistent blocked/completed statuses, and invalid issue code values raise `ValueError`.

The payload declares the research-only scope and fixed offline flags. It contains no live/provider client, broker, account, order, position, or trading data.
