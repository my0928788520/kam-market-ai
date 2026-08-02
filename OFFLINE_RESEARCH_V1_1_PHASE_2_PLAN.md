# Offline Research v1.1 Phase 2 — Fixture Runner + Result Export Plan

## Objective

Add an explicit local fixture runner on top of v1.1 Phase 1 CLI and the frozen v1.0 pipeline. The runner creates a deterministic result export for one user-supplied offline dataset and one user-supplied output path.

## Export contract

The export contains fixed export/CLI metadata, source/provider/dataset identity, pipeline hash, projection hash, complete deterministic pipeline JSON, and `export_hash`. The output path is operational only and is intentionally excluded from serialized metadata so an identical run has identical JSON across approved destinations.

## Safety policy

The output path must be absolute, use `.json`, have an existing parent directory, and not already exist. The runner refuses overwrite, missing-parent, relative-path, and non-JSON requests. It reads only the explicit local input path already supported by Phase 1 and performs no remote access.

## Frozen boundary

Phase 2 does not modify Provider Contract, Adapter, Historical Feed, Scan Engine, Scan Result, Dashboard Projection, or the v1.0 pipeline semantics. It adds no live provider, account, order, execution, or trading capability.
