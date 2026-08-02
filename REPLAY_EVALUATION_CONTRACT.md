# Replay Evaluation Contract

Evaluation version: `1.0`. Evaluation input is derived only from a Replay Frame.
Records retain source frame, timeframe, engine version, input/output hashes,
state, warnings, errors and lineage. EvaluatedReplayFrame wraps rather than
mutates the Phase 2 ReplayFrame.

No result is inferred from unavailable input. Decision output remains absent
until a later explicit frozen Decision adapter is supplied.
