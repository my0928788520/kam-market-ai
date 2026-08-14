# KAM Live TMF Paper Simulation — Safety and Performance Contract

## Scope

This phase connects the normalized, verified TMF five-timeframe candle result to
the existing Paper Trading proposal, manual-confirmation, risk, in-memory
matching, ledger, idempotency and audit boundaries. It never passes provider
objects, credentials, account data or broker clients into Paper Trading.

The production entrypoint always evaluates the current KAM states first. Only
the canonical `LONG / PAPER_BUY / eligible=true` result may build a simulated
BUY proposal. `HOLD`, incomplete alignment, stale data, future timestamps,
off-tick prices and the existing `SHORT` direction all fail closed without an
entry. Tests may supply a canonical direction directly to exercise deterministic
matching, but the live refresh path cannot override the KAM result.

## Manual arming

Paper simulation is disabled by default. The Windows launcher requires the
explicit `-PaperTestArmed` switch for the current local process. That switch is
the operator's manual approval for this paper-only session; it does not enable
live trading. Without both paper enablement and manual approval, a natural BUY
stops at `pending_manual_confirmation` and creates no fill.

## Fixed TMF policy

- Quantity: maximum one contract.
- Tick size: 1 point.
- Point value used by performance records: NT$10 per point.
- Initial stop loss: 20 points below the simulated entry.
- Initial take profit: 40 points above the simulated entry.
- Entry and exit matching price: the latest verified normalized 5-minute close.
- Maximum quote age: 360 seconds.
- Short paper entries: disabled in this phase.

The matching-price policy is explicit because the five-timeframe candle source
does not provide a bid/ask book. No synthetic spread or provider raw payload is
claimed or stored.

## Persistent journal

The local JSON journal stores only normalized paper state:

- simulated fills, cash ledger and position;
- entry, mark-to-market, stop-loss exit and take-profit exit events;
- entry/current/protection prices;
- unrealized and realized P&L, MFE and MAE using the TMF point value;
- proposal, quote, fill, event-chain, ledger and journal SHA-256 hashes;
- used idempotency keys.

Writes are atomic. Loading verifies the ledger hash, event chain and final
journal hash. A malformed, wrong-contract or modified journal is rejected; it
is never silently repaired. Repeated three-second refreshes of the same 5-minute
quote do not create duplicate fills or performance events.

## Permanent safety flags

Every quote, event, cycle result, ledger, request and fill remains:

- `dry_run=true`
- `live_order_allowed=false`
- `broker_connected=false`
- `account_credentials_allowed=false`
- application-level `trading_enabled=false`

There is no broker order placement, modification, cancellation or account-fund
capability in this phase.
