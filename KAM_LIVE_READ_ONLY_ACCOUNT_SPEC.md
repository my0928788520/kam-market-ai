# KAM Live Read-Only Account View

`/account` is a local GET-only futures-account viewer. It consumes only an `AccountReadOnlySource` and has no order, cancellation, close-out, fund-transfer, credential, network, or broker capability.

## Safety contract

- `live_order_allowed`, `broker_connected`, and `trading_enabled` are invariantly `false`.
- Account identifiers are only rendered from `account_masked`.
- `CapitalSafetyThresholds` is an immutable external policy input; no threshold belongs in HTML or CSS.
- Safety is fail-closed: disconnected, stale, unknown, or incomplete data always produces `UNKNOWN`.
- The initial page is explicit offline DEMO data: it says `示範帳戶資料・非真實帳戶・禁止真實交易` and `account_connected=false`.

## Read models

`FuturesAccountSnapshot` contains `AccountFunds`, `MarginUsage`, three product summaries (`TX`, `MTX`, `TMF`), source metadata, freshness, safety flags, and emergency-stop state. `AccountReadOnlySource` only exposes `read_snapshot()`.

## Minimum capital level and margin source

`MarginRequirementSource` is independent from `AccountReadOnlySource`.  It returns immutable
`MarginRequirement` snapshots with `product_code`, initial and maintenance margin,
`effective_at`, `source`, `fetched_at`, and `freshness`.  The display layer never owns
margin thresholds or source values.

For every open position, required margin is calculated from the absolute quantity:

- `required_initial_margin = sum(abs(quantity) * initial_margin)`
- `required_maintenance_margin = sum(abs(quantity) * maintenance_margin)`

The calculation includes TX, MTX, and TMF together.  It never depends on the market
instrument selected in the dashboard.

`CapitalSafetyThresholds` is immutable injected policy and includes
`initial_margin_multiplier`, `minimum_free_margin`, `maximum_margin_usage_ratio`, and
`warning_buffer_amount`.  Missing or stale account, position, or margin-source data is
always `UNKNOWN`.  `DANGER` applies when equity is at or below required maintenance margin,
or available margin is at or below zero.  `CAUTION` applies before `SAFE` whenever equity
does not clear the configured initial-margin buffer, usable margin is below the configured
minimum, or the configured usage limits are exceeded.  `SAFE` requires fresh, complete data
and all configured conditions to pass.

The account page shows summary values plus distances to caution and danger.  Per-product
margin values are deliberately contained in the collapsed **詳細資料** section.  This feature
only calculates, displays, and warns.  It cannot submit orders, close positions, transfer
funds, or perform automatic margin actions.

## KAM Account Center V1

`/account` is a server-rendered, GET-only Account Center.  It defaults to
`/account?view=overview` and exposes four mutually exclusive views:

- `overview`: compact account, funds, source, timestamp, and freshness summary.
- `water-level`: capital status and aggregate cross-product margin calculation.  Raw
  per-product margin data appears only at `?view=water-level&detail=1`.
- `position`: a single instrument only, defaulting to `TMF`; `TX`, `MTX`, and `TMF`
  are selected by GET query string.
- `settings`: immutable policy values and configuration provenance only.

Unknown views and invalid instrument codes render explicit fail-closed messages.  They are
never silently redirected to another view or product.  The footer uses human-readable
Traditional Chinese safety chips and never exposes internal boolean implementation strings.
