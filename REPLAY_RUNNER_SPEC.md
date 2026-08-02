# Replay Runner Contract

Runner version: `1.0`. The runner deterministically converts one valid Replay
Timeline into immutable Replay Frames. Its default and only executable Phase 2
mode is `input_only`: evaluation state is `not_evaluated`, and no engine,
Decision layer, account, market data or transaction capability is imported.

Run IDs are derived from scenario ID, timeline hash, runner/frame versions and
canonical configuration. The runner has no wall clock, random ID, thread,
async task, sleep or mutable global state. Invalid timelines fail closed.
Data gaps emit a gap frame and block by default. Source corrections emit a
corrected frame when valid.
