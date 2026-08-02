# Offline Research v1.1 Release Readiness

## Scope

v1.1 adds only the local CLI and explicit result export layer above frozen v1.0 research semantics. Replay, Fixture, JSON, and CSV remain the only supported input encodings.

## Readiness gates

- Explicit source, input path, output path, and overwrite policy are required for export mode.
- Default overwrite policy is `forbid`; `replace` is an explicit user choice.
- Success returns deterministic metadata and SHA-256 export hash.
- Failure returns stable `blocked` JSON with non-zero exit code and no implicit overwrite.
- End-to-end, deterministic, safety-boundary, and full repository tests pass.
