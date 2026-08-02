# Dashboard Presenter Release Note

Sprint 3 Phase 3 introduces Dashboard Presenter `1.0` and Dashboard WSGI Adapter
`1.0`. They consume only the Sprint 3 read model or serialization payload and
publish a deterministic, template-friendly dashboard contract.

This release adds semantic state classes, availability themes, accessible labels,
HTML escaping, fail-closed unavailable views, `no-store` WSGI metadata, and
development-only fixture loading. It does not alter the Decision layers, Read
Model, serialization schema, legacy Dashboard routes/templates, Position Parser,
or any trading capability.
