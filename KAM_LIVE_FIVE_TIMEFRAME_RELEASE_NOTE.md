# KAM Live Five-Timeframe Read-Only Decision — Release Note

## Release status

The live TMF five-timeframe path is ready for controlled read-only operation.
It retrieves only market data, analyzes `5m`, `15m`, `60m`, `1d`, and `1w`,
maps each slice into the canonical KAM states, and presents one observation
direction and one next step.

## Delivered

- Canonical `AU/AF/AD/NU/NF/ND/BU/BF/BD` mapping with traceable evidence.
- Read-only KAM direction: `偏多`, `偏空`, or `觀望`.
- Exactly one next observation step.
- Local dashboard and no-store JSON endpoint.
- Automatic active TMF contract resolution with ambiguity rejection.
- Atomic safe snapshots with freshness enforcement.
- Periodic refresh recovery: failed calls never replace the last verified
  snapshot, and subsequent cycles retry automatically.
- Explicit degradation for unusable input, analysis error codes, stale data,
  invalid data, calculation errors, and higher-timeframe conflict.

## Safety boundary

- `market_data_only=true`
- `trading_enabled=false`
- `live_order_allowed=false`
- Final action is always `HOLD`.
- Bearish analysis is observable, but no short strategy or `SELL` action is
  enabled.
- No account, broker, order placement, modification, cancellation, or closing
  capability is part of this release.

## Validation

The full automated test suite, focused state-mapping tests, snapshot freshness
tests, repeated refresh failure tests, recovery tests, Python compilation, and
Git diff whitespace validation must pass before publishing this release.
