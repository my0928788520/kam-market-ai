# KAM Trade V3 — Next Step Engine Foundation

## Purpose

The Next Step Engine converts Contract, Confidence, and Risk diagnostics into the next observation or verification task. It is explicitly not a trading recommendation or instruction.

## Inputs and validation

`evaluate_next_step(contract, confidence, risk, config)` requires matching supported versions, matching timezone-aware evaluation time, and fixed timeframe source coverage. Type/version/time mismatches return `invalid` immediately.

## Output vocabulary

Output uses only observation-safe actions: maintain observation, wait for candle close, wait for confirmation, verify breakout/breakdown/retest, review trend/structure, pause decision, market-closed wait, insufficient-data wait, no-action-required, unavailable, invalid, and calculation error. It never emits buy, sell, long, short, enter, exit, order, stop, target, sizing, or risk limit.

## Priority

Priority is deterministic: invalid/stale source, higher-timeframe conflict, timeframe/module conflict, wait for close, provisional timing, trend/structure review, then maintain observation. NextStepType is separate from operational state; `maintain_observation` is not an entry condition and `pause_decision` is not a direction claim.

## Configuration and fail-closed boundary

Supported source versions and full priority order are typed configuration and validated. All priority mappings are **PROVISIONAL**. Dashboard/API, market data, replay, user settings, AI, account access and all orders are excluded.
