# Replay Timeline Contract

Version: `1.0`. `build_replay_timeline` validates a static scenario and orders
events by occurrence time, event-type priority, source priority, stable sequence
and deterministic event ID. It emits a SHA-256 timeline hash and optional fixed
duration from scenario boundaries.

The timeline is not a runner: it has no wall clock, playback, pause, scrubber,
animation, chart, engine invocation or decision calculation.
