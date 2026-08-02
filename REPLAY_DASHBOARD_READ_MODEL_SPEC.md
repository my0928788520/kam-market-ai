# Replay Dashboard Read Model

Version 1.0 is an immutable, read-only conversion from an `EvaluatedReplayFrame` plus an optional prior frame. It exposes progress, hero, decision summary, four fixed timeframe cards, four fixed module cards, comparison data, and bounded state messages. It never invokes Engines or Decision callables and provides unavailable values as null rather than neutral or zero.

It has no Presenter, UI, routes, controls, charts, market feeds, or transaction behavior. Comparison describes change only; it does not classify a change as better, safer, or actionable.
