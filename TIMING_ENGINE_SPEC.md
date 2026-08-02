# KAM Trade V3 — Timing Engine Foundation

## Scope

`src/kam_market_ai/analysis/timing_engine.py` is a deterministic, offline timing classifier for 15m, 60m, 1d, and 1w candle inputs. It contains no SDK, quote, order, Dashboard/API, Position, Trend, Structure, risk, or decision logic.

## Time and session contract

All datetimes must be timezone-aware and are interpreted in `Asia/Taipei`; naive or incompatible input fails closed. The provisional schedule is day `08:45–13:45`, night `15:00–05:00`, with 15-minute pre-open, opening, and pre-close windows. `SessionType` is `day`, `night`, `closed`, `pre_open`, `break_period`, or `unknown`; `MarketPhase` includes pre-open, opening, regular, pre-close, closed, session transition, unknown, and invalid.

Night trading date belongs to the following calendar date: a 15:00 session on Monday and the 00:00–05:00 continuation on Tuesday both resolve to Tuesday. Weekend and holiday behavior is typed policy. The built-in schedule is **PROVISIONAL**; holidays and exceptional sessions are adapter boundaries, not inferred exchange-calendar truth.

## Candle, freshness, and readiness

The latest candle is `closed`, `forming`, `future`, `overdue`, `missing`, or `invalid`. Only a closed, fresh candle makes `close_confirmation_available=True`; forming data is never confirmation. Overdue is determined from the observed candle duration plus per-timeframe grace, without inventing a timeframe duration. Freshness states are fresh, delayed, stale, future, unknown, and invalid. Provisional delays/stale thresholds are 15m `5m/30m`, 60m `15m/2h`, 1d `6h/2d`, and 1w `2d/14d`.

`TimingReadiness` is confirmed, provisional, wait-for-close, market-closed, delayed, stale, insufficient-data, ambiguous, invalid, or calculation-error. A forming candle becomes `wait_for_close` only where the typed configuration requires closure; otherwise it is provisional. Fresh, closed in-session data is confirmed. No readiness state is a trade instruction.

## API and output

`evaluate_timing(timeframe, candles, evaluated_at, config)` returns `TimingResult`, including calendar/trading dates, session boundaries, minute offsets, candle timing fields, freshness diagnostics, readiness, reused `DataStatus`, validity and warnings. `evaluate_all_timings` evaluates every timeframe independently and converts any isolated exception to a calculation-error result.

## Fail-closed behavior

Naive datetime, invalid or zero-duration candle, out-of-order input when sorting is disabled, duplicate timestamp, overlap, incompatible timestamp, future data, missing data, stale data, unknown holiday, and invalid configuration are explicit diagnostics. Sorting and duplicate retention are available only through typed policy. All session times, thresholds, grace periods, and calendar integration remain **PROVISIONAL** pending a supplied official calendar source.

## Downstream boundary

Timing output is reserved for later consumption by Position, Trend, Structure, Timing/Decision layers. This phase does not connect them and does not add Decision Confidence, Risk, Next Step, AI summaries, or any order capability.
