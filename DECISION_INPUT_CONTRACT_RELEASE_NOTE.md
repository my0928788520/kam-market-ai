# Decision Input Contract Foundation — Release Note

## Delivered

- Added `kam_market_ai.decision` and Contract version `1.0`.
- Added typed module, timeframe, normalized-state, confirmation-state, status and policy models.
- Added read-only adapters for Position, Trend, Structure and Timing results, complete four-timeframe aggregation, raw-state traceability and fail-closed diagnostics.

## Verification

Run `python -m pytest tests/test_decision_contract.py -q`, then `python -m pytest -q`.

## Boundary

This phase does not add Decision Confidence, Risk, Next Step, trading instructions, SDK access, market-data access, Dashboard/API integration, or order capability. Existing Engines and `KAM_V1.6_fubon_bridge` remain unchanged. Configuration policy is **PROVISIONAL** until a later, separately approved decision-layer scope.
