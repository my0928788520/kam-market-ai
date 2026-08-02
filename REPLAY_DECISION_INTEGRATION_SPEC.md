# Replay Decision Integration Boundary

Phase 3 establishes the boundary for future frozen Decision invocation without
inventing new Confidence, Risk or Next Step semantics. Engine evaluation records
are typed and deterministic; unavailable or invalid inputs fail closed. The
current adapter intentionally leaves `decision_evaluation` absent rather than
guessing decision results.
