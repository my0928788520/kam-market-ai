# Replay Fixture Contract

Fixture version: `1.0`. Fixtures are JSON metadata in `tests/fixtures/replay`.
Loading is restricted to a fixed whitelist and rejects path traversal, arbitrary
file names and invalid metadata. Fixtures contain no credentials, account data,
API keys, tokens, private paths or transaction instructions.

Fixture changes must preserve deterministic metadata and update tests. Changing
the contract shape is a major-version change.
