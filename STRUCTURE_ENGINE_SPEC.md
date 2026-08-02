# KAM Trade V3 — Structure Engine Foundation

## Purpose and scope

`src/kam_market_ai/analysis/structure_engine.py` is an offline, read-only structure classifier for the independent `15m`, `60m`, `1d`, and `1w` candle streams. It consumes the existing confirmed `Pivot` model and `detect_confirmed_pivots`; it does not create a second pivot detector, contact an SDK, query market data, or produce trading decisions.

## Inputs and Pivot contract

`evaluate_structure(timeframe, candles, current_price, evaluated_at, config, precomputed_pivots=None)` accepts only completed candles (`end <= evaluated_at`) as confirmation evidence. An optional pivot sequence must be ordered, confirmed, have the same timeframe, and match the corresponding candle timestamp and high/low exactly. Otherwise the result is `invalid`. Without supplied pivots, the existing detector is used. The aggregator, `evaluate_all_structures`, evaluates every timeframe independently and contains a single-timeframe failure.

## Swing and sequence rules

Highs compare only with prior highs; lows compare only with prior lows. Values outside the configured tolerance become `HH`/`LH` or `HL`/`LL`; values inside it become `EQH`/`EQL`; the first pivot of either kind is `unclassified`. `HH + HL` is bullish continuation, `LH + LL` bearish continuation. Equal, mixed, insufficient, or conflicting evidence is neutral/ambiguous/insufficient rather than directional.

## Patterns and neckline

A W Bottom is confirmed-pivot `low A → high B → low C`; M Top is `high A → low B → high C`. A and C must meet similarity, leg-distance, height, and invalidation rules. The current version has one horizontal neckline: B for W and B for M. A completed close must remain above/below neckline plus/minus tolerance for the configured confirmation-bar count to produce `confirmed`. `current_price` can only give a provisional neckline relation; it cannot confirm a break.

Second low below A beyond invalidation tolerance, second high above A beyond tolerance, expired candidate, invalid pivot, stale data, or ambiguity causes fail-closed output. Candidate scoring is internal quality only (recency, leg symmetry, similarity, height, confirmed pivots, neckline proximity, invalidation); it is explicitly not Decision Confidence.

## Output

`StructureResult` contains timeframe, pivots, swing points, latest labels, sequence and bias, W/M pattern results, active pattern, neckline, price/time/counts, `DataStatus`, stale/valid flags and warnings. Enums include `SwingLabel`, `SequenceState`, `StructureBias`, `PatternType`, `PatternState`, and `NecklineRelation`. `DataStatus` reuses the Phase 1 enum: `ok`, `insufficient_data`, `stale`, `invalid`, and `calculation_error`.

## Provisional configuration

`StructureEngineConfig.provisional()` is typed and validated. All numerical settings are **PROVISIONAL**: 15m `96/48/5/.30/.10/.25/.40/3/32/2/24`; 60m `72/36/5/.35/.12/.30/.50/3/24/2/18`; 1d `90/45/5/.50/.20/.45/1.00/3/30/2/15`; 1w `78/39/5/.75/.30/.70/2.00/2/20/1/10` (lookback/min closed/min pivots/similarity%/neckline%/invalidation%/minimum height%/min-max legs/confirmation/max age). Swing tolerance is separately configurable. Candidate weights, pivot windows, sorting and duplicate policy are also typed and validated.

## Fail-closed and future interfaces

NaN/infinity, malformed prices, high-low-close contradictions, zero duration, overlap, duplicate timestamps, incompatible timezones, wrong/unconfirmed/misaligned pivots, missing data, stale data, and ambiguous candidates never become directional structure. No Position Engine or Trend Engine code was altered. Future consumers may read `StructureResult`, but Timing, Decision Confidence, Risk, Next Step, Dashboard/API integration, AI, and all order functions remain out of scope.

## Known provisional items

Market-specific tolerances, candidate weights, plateau handling, pivot windows, and stale thresholds require later historical validation. Only horizontal necklines exist; sloped necklines and other chart patterns are intentionally excluded.
