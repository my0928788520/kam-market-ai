# Sprint 5 Phase 1 — Market Data Provider Contract

Added a deterministic, research-only provider data contract at `kam_market_ai.market_data.provider_contract`.

The release contains immutable provider, request, bar, and response value objects plus a deterministic response hash. It admits only fixture/replay sources and fails closed when source capability, timing, bar integrity, ordering, or response evidence is invalid.

No provider implementation, SDK call, network operation, account/order capability, persistence integration, or trading behavior was added.
