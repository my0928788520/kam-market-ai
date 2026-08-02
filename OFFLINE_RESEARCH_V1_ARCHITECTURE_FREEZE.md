# Offline Research v1.0 Architecture Freeze

```text
Provider Contract
  -> Offline Provider Adapter (Replay | Fixture | JSON | CSV)
  -> Historical Feed / Offline Dataset
  -> Market Data Scan Engine
  -> Scan Result Read Model
  -> Dashboard Projection
```

The pipeline entrypoint only accepts an existing provider contract, offline dataset, and ready scan plan. It only returns the scan result and dashboard projection with deterministic lineage hash.

Frozen boundaries: no changes to Replay, Decision, existing Dashboard, Fubon adapter, or trading modules are part of Offline Research v1.0. No network client, live provider, broker, account, order, position, execution, or funding capability may cross this boundary.
