# Decision Confidence Engine Foundation — Release Note

## Delivered

- Added Decision Confidence Engine version `1.0`, typed configuration, module contributions, timing gate, timeframe confidence and overall alignment.
- Added Decimal-only deterministic scoring, score clamping, quality-hint policy, reason codes, conflict penalties and fail-closed operational states.
- Added focused offline tests for aligned direction, provisional/stale/invalid handling, contract mismatch, neutral/mixed results, hints, and config validation.

## Compatibility and safety

Decision Input Contract and all Sprint 1 engines remain unmodified. The engine performs no SDK, market-data, account, Dashboard/API, Risk, Next Step, AI, or order action. Existing `HardGate` behavior remains unchanged.

## Verification

Run `python -m pytest tests/test_decision_confidence.py -q`, then `python -m pytest -q`.

All scoring weights, thresholds, penalties, and timing multipliers are **PROVISIONAL** pending separately authorized historical validation.
