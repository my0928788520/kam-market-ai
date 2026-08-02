# KAM Trade V3 — Decision Input Contract 1.0

## Purpose

The Decision Input Contract is a typed, read-only adapter boundary between the Position, Trend, Structure, and Timing Engines and a future Decision Engine. It normalizes module output; it does not calculate confidence, risk, next step, signals, orders, or UI/API output.

## Contract

`DECISION_INPUT_CONTRACT_VERSION = "1.0"`. `build_decision_input_contract(position_results_by_timeframe, trend_results_by_timeframe, structure_results_by_timeframe, timing_results_by_timeframe, evaluated_at, config)` emits every required fixed timeframe and a `DecisionInputContract`. Each `TimeframeDecisionInput` contains exactly position, trend, structure, and timing inputs plus completion, usability, warnings, errors, and status.

Each `DecisionModuleInput` preserves module/timeframe, availability, validity, source type/version, evaluated timestamp, warnings, error code, raw state/status and its normalized state. `confidence_hint` is pass-through metadata only: Trend confidence and Structure candidate quality are not Decision Confidence; Timing does not supply a confidence value.

## Normalization

- Position: upper/near-high → bullish; lower/near-low and breakdown → bearish; breakout → supportive; middle → neutral.
- Trend: ascending → bullish; descending → bearish; no trend → neutral; ambiguous remains ambiguous. Broken/retest/rejection are retained in raw state.
- Structure: bullish sequence or confirmed W → bullish; bearish sequence or confirmed M → bearish; range → neutral; mixed → conflicting; candidates/testing → provisional; ambiguous remains ambiguous.
- Timing: confirmed → confirmed; provisional → provisional; wait-for-close → waiting; delayed/stale → stale; invalid/error → invalid/error. Market-closed policy is typed and defaults to waiting.

## Status and fail-closed

`DecisionInputStatus` priority is invalid, calculation-error, stale, ambiguous, partial, provisional, ready (with unavailable retained when the minimum module count cannot be met). Missing, wrong type, mismatched evaluated-at, naive evaluated-at, unsupported version, invalid data status, and unknown input never become ready. One bad module/timeframe is isolated; the contract still includes all required timeframes.

## Configuration

`DecisionInputConfig.provisional()` centralizes required modules/timeframes, minimum usable module count, timing confirmation, provisional/partial policies, stale/ambiguous/unknown fail-closed policies, market-closed behavior, raw preservation and warning limits. These policies are **PROVISIONAL** and do not encode trading rules.

## Compatibility

Breaking contract changes require a major version. Source versions are explicit contract metadata rather than a Git hash. Existing Engine files are not changed; adapters validate their result type before reading fields.
