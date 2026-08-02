# Offline Research v1.1 Architecture Freeze

```text
Explicit local input
  -> pipeline_cli
  -> frozen Offline Research v1.0 pipeline
  -> Fixture Runner / explicit local JSON export
```

The v1.1 layer may parse an explicit local path and write one explicit local export path. It does not alter Provider Contract, Adapter, Historical Feed, Scan Engine, Scan Result, Dashboard Projection, or pipeline semantics. No remote transport, live source, broker, account, order, position, or trading boundary is admitted.
