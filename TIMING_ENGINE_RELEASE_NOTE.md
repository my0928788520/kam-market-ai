# Timing Engine Foundation — Release Note

## Delivered

- Added independent offline session, trading-date, candle-state, freshness, and readiness classification.
- Added Taiwan-time provisional day/night schedule and four-timeframe aggregation.
- Added fail-closed validation and deterministic tests for session boundaries, candles, freshness, readiness, calendar states, malformed inputs, and failure isolation.

## Safety and compatibility

No existing Position Engine, Pivot/Trend Engine, Structure Engine, Position Parser, Dashboard, API, credentials, or `KAM_V1.6_fubon_bridge` code changed. No network, SDK, market-data, account, or trading action is used.

## Verification

Run `python -m pytest tests/test_timing_engine.py -q`, then `python -m pytest -q`. All session hours, thresholds, weekend/holiday handling, and exceptional-session support are marked **PROVISIONAL** until an approved official calendar adapter is supplied.

## Next boundary

The next sprint may define a read-only consumer for `TimingResult`; it must retain the distinction between confirmed and provisional data and must not treat timing readiness as an order signal.
