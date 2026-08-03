# KAM Trade Sprint 1 — Rule Adapter

The adapter is a deterministic, offline-only gate between KAM timeframe state
and the existing Paper Order Proposal contract. Emergency stop, stale or
missing data, risk blockers, U0/U5-U7, bearish higher timeframes without an
approved short strategy, and invalid BUY protection all fail closed to HOLD.
Only fully aligned AU weekly/daily/60/15/5 state produces a BUY proposal, which
still requires Phase 1 manual confirmation and safety before matching.
