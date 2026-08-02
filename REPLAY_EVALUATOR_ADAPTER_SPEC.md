# Replay Evaluator Adapter

Version: `1.0`. The adapter accepts an explicit frozen engine callable bundle
and immutable Replay Frame input. It invokes Position, Trend, Structure and
Timing in stable timeframe/module order, records hashes and lineage, and fails
closed on missing input, exception or partial output.

Replay never reflects imports, contacts a service or changes frozen engines.
