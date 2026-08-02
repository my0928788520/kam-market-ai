# Market Data Dashboard Projection — Sprint 5 Phase 6

## Scope

The projection is an immutable, read-only view of an existing `MarketDataScanResult`. It does not re-run a scan or access a dataset. The UI-facing model contains only overall status, scan counts, per-instrument summaries, and issue summaries.

## Determinism

Batches are checked against the original plan. Instruments are unique and ordered canonically; issues are de-duplicated and ordered by instrument, severity, and code. `serialize()` emits compact sorted JSON. `projection_hash` is SHA-256 over the canonical payload.

## Fail-closed and compatibility policy

The accepted source is exactly `MarketDataScanResult` and the Scan Engine/Projection versions must match. Duplicate instruments, missing batches, invalid feed membership, skipped batch feeds, inconsistent execution status, invalid counts, and noncanonical issues raise `ValueError`.

The payload declares `MARKET_RESEARCH_ONLY`, with network and live-provider flags fixed to false. No decision, signal, trade, provider client, account, order, or position information is projected.
