# Paper Trading v0.1 Phase 1 — Trading Safety Contract

## Scope

Phase 1 is an isolated contract and deterministic safety-evaluation boundary. It models paper requests, results, fills, positions, account snapshots, risk limits, safety state, and audit events. It does not connect to any external execution system.

## Safety policy

Every request is dry-run only. Live permission, connectivity, and account-credential permission are fixed false in every relevant contract. The default safety state disables paper trading and enables the emergency stop, so a request is rejected unless a caller explicitly supplies an enabled, non-emergency state with complete risk context.

The evaluator checks version, UTC timestamp, idempotency, allowed instrument/session, maximum quantity/notional/daily loss/open positions, and safety flags. Results are accepted or rejected only; acceptance represents no external action.

## Determinism

All contracts are frozen dataclasses, use `Decimal` for financial values, serialize canonical payloads, and derive SHA-256 hashes. Evaluation time is the supplied request timestamp; no runtime clock, random ID, remote access, or mutable global state is used.
