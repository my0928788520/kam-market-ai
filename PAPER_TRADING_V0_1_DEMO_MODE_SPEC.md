# Paper Trading v0.1 Morning Session Demo Mode

`--demo` loads only fixed, module-defined data marked `DEMO`. It is explicitly
not real-time market data and is solely for local layout, workflow, and
in-memory matching acceptance. The default startup remains the empty view.

All proposal, snapshot, fill, and ledger values are deterministic. The mode
keeps dry-run enabled and disables live order, broker connection, and trading.
