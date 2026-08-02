# Structure Engine Foundation — Release Note

## Delivered

- Added an offline Structure Engine using the existing confirmed Pivot contract.
- Added HH/HL/LH/LL/EQH/EQL swing labeling, sequence/bias classification, W Bottom and M Top candidates, horizontal neckline relation, confirmation, invalidation, ambiguity handling, and four-timeframe aggregation.
- Added typed, validated **PROVISIONAL** configuration and deterministic offline tests.

## Safety boundary

No SDK, quote, account, order, Dashboard, API, Position Parser, Position Engine, or Trend Engine behavior changed. The feature contains no order capability and does not call any external service.

## Verification

Run `python -m pytest tests/test_structure_engine.py -q` for the Structure Engine tests, then `python -m pytest -q` for the complete repository suite. The implementation fails closed for invalid, stale, insufficient, and ambiguous inputs.

## Follow-up

Before any downstream use, validate provisional thresholds and weights against retained historical MTX candles. A later sprint may consume the output for a clearly scoped timing/decision layer; it must not reinterpret internal candidate quality as trading confidence.
