# Offline Research v1.1 Phase 1 — Pipeline CLI Plan

## Objective

Provide one explicit local command-line entrypoint for the frozen Offline Research v1.0 flow. Phase 1 adds presentation and invocation only; it does not alter v1.0 component semantics or version compatibility.

## Supported input

The CLI accepts a user-supplied local path plus source encoding `replay`, `fixture`, `json`, or `csv`. Replay and fixture paths contain a JSON array of bar mappings; JSON paths contain the same array; CSV uses the existing offline adapter header schema. The path is explicit: there is no directory discovery or background loading.

## Pipeline

`python -m kam_market_ai.market_data.pipeline_cli` constructs existing offline source, provider, dataset, and scan-plan values, then calls only `run_offline_research_pipeline`. It writes one compact deterministic JSON document to standard output containing pipeline and dashboard-projection hashes and payloads.

## Safety and compatibility

All content remains local and offline. Invalid source content produces a deterministic blocked JSON response and exit code `2`. No v1.0 core file is changed. There is no remote transport, live source, broker, account, order, position, decision, or trading behavior.
