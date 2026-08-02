# Replay Frame Serialization Contract

Version: `1.0`. Frame and run serialization is JSON-safe and deterministic.
Enums use stable values, aware datetimes use ISO 8601, tuples use arrays and
timedeltas use seconds. Canonical JSON never includes Python reprs, runtime
metadata, credentials, account fields or private paths.
