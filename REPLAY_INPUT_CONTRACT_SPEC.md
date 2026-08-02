# Replay Input Contract

Version: `1.0`. Replay Input is a frozen, read-only historical scenario
contract. It defines immutable scenario, event and timeframe-snapshot values;
it neither invokes engines nor produces decisions.

The only timeframes are `15m`, `60m`, `1d`, and `1w`. Events use deterministic
hash IDs, one-based contiguous sequences, aware `ZoneInfo` timestamps and a
strict scenario timezone. Unsupported versions, naive timestamps, timezone
mismatches, duplicates, out-of-range events and unsupported sources fail closed.

Snapshots retain opaque module input mappings only. They are not module outputs,
decisions, account state, transaction data or a replacement module schema.
