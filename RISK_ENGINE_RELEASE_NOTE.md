# Risk Engine Foundation — Release Note

- Added Risk Engine version 1.0 with typed config, contribution trace, risk level, operational state, hard floors and source-integrity blocks.
- Added deterministic offline tests for valid input, wait-for-close floor, conflict floor, invalid source and mismatch protection.
- No existing Engine, Contract, Confidence logic, HardGate, Dashboard/API, SDK, account, market-data or trading behavior was changed.

Run `python -m pytest tests/test_risk_engine.py -q`, then `python -m pytest -q`. All risk weights and thresholds are **PROVISIONAL**.
