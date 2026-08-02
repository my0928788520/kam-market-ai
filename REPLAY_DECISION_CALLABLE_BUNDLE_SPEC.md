# Replay Decision Callable Bundle

Phase 3B adds a frozen, explicitly injected callable boundary for the existing Decision Input, Confidence, Risk, and Next Step public APIs. `FrozenDecisionCallableBundle` stores callables and declared versions only; it never resolves import paths, uses reflection, performs I/O, or supplies fallback decisions.

The adapter accepts exactly four valid engine outputs for each of 15m, 60m, 1d, and 1w. It maps them deterministically by module and timeframe, invokes Decision Input → Confidence → Risk → Next Step once, and records canonical SHA-256 hashes. Any missing, invalid, unsupported, or throwing dependency produces a fail-closed `ReplayDecisionEvaluation`; downstream calls are not attempted. Engine-only replay remains valid with `decision_evaluation=None`.
