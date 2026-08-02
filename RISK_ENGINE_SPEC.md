# KAM Trade V3 — Risk Engine Foundation

## Scope

`evaluate_risk(contract, confidence, config)` is a read-only deterministic diagnostic over Decision Input Contract 1.0 and Decision Confidence 1.0. It does not generate an order, risk limit, position size, stop, target, Next Step, API/Dashboard response, or external request.

## Validation and hard blocks

Contract/confidence types, supported versions, matching timezone-aware `evaluated_at`, fixed timeframe presence and confidence counterpart are checked first. A source mismatch or unsupported version returns invalid risk without a calculation fallback. Invalid source states are fail-closed.

## Risk model

All values are **PROVISIONAL** Decimal configuration. Category weights are data quality .20, timing .15, position .15, trend .10, structure .15, module conflict .15 and coverage .10. Timeframe weights are 15m .15, 60m .25, 1d .35 and 1w .25. The output preserves category contributions, raw reasons, timeframe scores, overall score, level, and operational state.

Timing waiting has a floor of 30; module conflict has a floor of 50; stale/invalid source risk is elevated with a stale floor of 65. Confidence is uncertainty input rather than a direct `100 - confidence` replacement. Overall risk additionally carries timeframe and higher-timeframe conflict diagnostics.

## States

Risk levels are minimal, low, moderate, elevated, high, critical, unavailable, stale, invalid and calculation-error. Operational state is separate: valid, provisional, waiting, conflicting, stale, insufficient, invalid and calculation-error. Scores are clamped to 0–100 and rounded using Decimal.

## Deferred work

Thresholds, position distance/extreme rules, detailed trend/structure risk rules, calendar phase policy, risk limits, sizing, stops, orders, user preferences, real-time data, replay and AI are explicitly deferred.
