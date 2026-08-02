# Sprint 5 Phase 2 — Market Data Provider Adapter

Added the pure `adapt_offline_market_data` adapter for replay, fixture, JSON, and CSV content. It transforms validated in-memory rows into the Sprint 5 Phase 1 provider response contract with deterministic ordering and hash behavior.

Malformed or unsupported offline content is reported as a fail-closed blocked response. No network, file access, live provider, credential, account, order, or trading capability was added.
