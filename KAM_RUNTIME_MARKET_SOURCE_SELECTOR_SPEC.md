# Sprint 7 / Sprint 9B Runtime Source Selector

The runtime defaults to `offline-demo`. `fake-live` is explicit, local,
deterministic, and read-only. `fugle-live` remains reserved and has no available
products or fallback.

`fubon-live` is an explicit Windows-local Sprint 9B source. It requires both the
source choice and `--live`, accepts only an already-authorized market-data client,
and starts only after TX, MTX, and TMF contracts have been verified. Environment
variables cannot select or activate it implicitly. The provider exposes only
`MarketSnapshot`, runtime status, product listing, and lifecycle cleanup. It has
no account, order, position, balance, or trading capability.
