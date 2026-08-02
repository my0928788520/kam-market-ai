# Paper Trading v0.1 Phase 4 — Local Operator Frontend

The operator frontend is a local, GET-only WSGI view bound by the optional
launcher to `127.0.0.1`. It presents proposal, matching, ledger, and audit
summaries with escaped HTML. There are no confirmation, order, broker, or
network-provider endpoints. The server is never started on import.
