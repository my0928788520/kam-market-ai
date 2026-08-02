# Replay Presenter Serialization

Version 1.0 canonicalizes typed presenter views as JSON-safe UTF-8 data with sorted keys, enum values, and arrays. The serialization config bounds payload size and controls warnings, errors, accessibility, and compact/pretty output. No HTML fragments, local paths, callable representations, or stack traces are emitted.
