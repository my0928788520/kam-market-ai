# Replay Frame Contract

Frame version: `1.0`. Each frame retains source event lineage, deterministic
frame sequence, previous frame ID/hash and own SHA-256 hash. All four timeframe
slots are present. Unchanged slots carry forward only prior safe input state;
unavailable, invalid and gap-affected slots never silently inherit data.

Frame states include scenario boundaries, active, unchanged, partial update,
gap, corrected, stale, invalid, blocked and completed. Frames contain no
decision input/result/dashboard output in Phase 2.
