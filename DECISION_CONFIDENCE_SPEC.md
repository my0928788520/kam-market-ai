# KAM Trade V3 — Decision Confidence Engine 1.0

## Purpose and boundary

The Decision Confidence Engine consumes only `DecisionInputContract 1.0` and produces deterministic, explainable confidence diagnostics. It is not a signal, order, entry/exit, Risk, Next Step, AI, Dashboard, or API component.

## Inputs and output

`evaluate_decision_confidence(contract, config)` validates contract version and timezone-aware evaluation time, then returns fixed 15m/60m/1d/1w `TimeframeConfidenceResult` values and one `DecisionConfidenceResult`. Directions are bullish, bearish, neutral, mixed, unavailable, or invalid. Confidence state is separate from score level, so a high numerical score may still be operationally provisional, stale, conflicting, or invalid.

## Provisional scoring

All values are **PROVISIONAL**. Module weights are Position .20, Trend .35, Structure .35, Timing .10; timeframe weights are 15m .15, 60m .25, 1d .35, 1w .25. Position, Trend and Structure are directional; Timing is a gate. Confirmed/provisional/waiting timing multipliers are 1.00/.75/.50; stale, invalid, and calculation-error are zero.

For each timeframe, directional contributions use base weight × quality multiplier × timing gate. Quality uses a finite Decimal source hint when within configured range, otherwise typed default confirmation quality. A bad hint is rejected or clamped by policy. Score is deterministic Decimal arithmetic, clamped to 0–100, reduced for conflict/ambiguity, and rounded to configured precision.

## Alignment and fail-closed

Bullish/bearish timeframe weights produce alignment: fully aligned, mostly aligned, partially aligned, conflicting, neutral, insufficient, stale, or invalid. Any module-level bullish/bearish conflict is `mixed`, never resolved merely by a larger weight. Invalid contract/timeframe, stale input, unsupported version, naive timestamp, missing timeframe, out-of-range hint (under reject policy), ambiguity, insufficient coverage, and calculation errors stay explicit in state, warnings, errors, and reason codes.

## Explainability

Each contribution retains base/quality/confirmation/effective weights, directional/neutral contribution, inclusion/exclusion, source raw state/status and warnings. Output includes supports/conflicts and stable reason codes. Trend/Structure hints are input quality only and are not Decision Confidence themselves.

## Deferred work

Thresholds, conflict penalties, quality rules, and calendar consequences require historical validation. Risk, Next Step, replay, user settings, execution, market-data access, AI/LLM, and all order behavior are deliberately excluded.
