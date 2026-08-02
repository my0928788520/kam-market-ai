# Replay Phase 3B Release Note

Phase 3B completes frozen replay evaluation through the existing Decision layer. It introduces an immutable callable bundle and a fail-closed adapter that preserves source-frame and bundle lineage, evaluates only complete engine sets, and serializes the resulting `ReplayDecisionEvaluation` through the existing evaluation serializer.

No decision semantics, engine contracts, UI, APIs, brokerage access, or transaction capability were added or changed. The remaining limitation is intentional: callers must explicitly provide config-bound existing Decision callables.
