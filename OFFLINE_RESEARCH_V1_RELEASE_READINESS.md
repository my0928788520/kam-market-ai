# Offline Research v1.0 Release Readiness

## Scope gate

The release is offline, research-only, deterministic, and read-only. The supported flow is Provider Contract → Provider Adapter → Historical Feed → Scan Engine → Scan Result Read Model → Dashboard Projection. It accepts only explicit Replay, Fixture, JSON, or CSV in-memory content.

## Readiness checks

- Contract and component version matrix is fixed at 1.0.
- Pipeline accepts only an existing provider contract, offline dataset, and ready scan plan with matching lineage.
- Plan, scan, result, projection, and pipeline outputs have deterministic SHA-256 lineage hashes.
- BLOCKED and COMPLETED_WITH_ISSUES states are preserved; partial results cannot become COMPLETED.
- Unit, integration, determinism, safety, and architecture-boundary tests pass.
- No runtime credential, live source, persistence, decision, or execution capability is in the pipeline.

## Release decision

Ready for Offline Research v1.0 release candidate validation after the repository-wide pytest and whitespace checks pass in the release environment.
