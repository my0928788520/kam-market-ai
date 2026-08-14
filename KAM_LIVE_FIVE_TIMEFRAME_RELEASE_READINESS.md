# KAM Live Five-Timeframe Read-Only Release Readiness

## Automated acceptance

- [x] Fubon intraday boundary calls only documented candle parameters.
- [x] Regular session omits the provider session token.
- [x] After-hours requests use the verified provider token.
- [x] Active TMF contract resolution fails closed on ambiguity.
- [x] Five timeframe analysis maps to exactly nine canonical KAM states.
- [x] Unusable, stale, invalid, conflicting, or error-bearing frames degrade.
- [x] Direction is limited to `偏多`, `偏空`, or `觀望`.
- [x] Exactly one next observation step is presented.
- [x] Safe snapshots are atomic, no-store, fresh, and exclude raw candles.
- [x] Failed refreshes preserve the last verified snapshot and retry.
- [x] Health reporting excludes exception text and credentials.
- [x] Provider-to-dashboard cross-layer acceptance passes.
- [x] Full automated test suite passes.
- [x] Python compilation and Git diff whitespace validation pass.
- [x] Railway deployment reports success.

## Permanent release boundary

- `market_data_only=true`
- `trading_enabled=false`
- `live_order_allowed=false`
- `action=HOLD`
- No account connection or order capability.
- Bearish output is observation-only; no short strategy is approved.

## Operational evidence still accumulated over time

Multi-session day/night observation, real provider outages, and contract-roll
events are operational monitoring evidence. They do not block this read-only
release and must not be used to silently widen trading authority.
